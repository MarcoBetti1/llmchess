"""
RUN.py — Experiment runner
- Sweeps one or more JSON config files and runs multiple chess games per config.
- Sequential mode only: one chat/completions call per turn until the game ends.
- Opponents: another LLM (provider-agnostic) or a local human user.
- Writes per-game conversation/history logs and aggregates results to <out_dir>/results.jsonl.
- Respects per-config log_level and out_dir (no CLI overrides).
- Prints a grand summary (W/D/L, avg plies, legal rate, latency, wall time).
Usage: python -u scripts/run.py --configs "tests/*.json"
Env knobs: LLMCHESS_MAX_CONCURRENCY, LLMCHESS_RESPONSES_TIMEOUT_S, etc.
"""
import argparse, json, logging, os, sys, glob, statistics, time
import copy
from typing import List, Dict

# Ensure project root added
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.llmchess_simple.game import GameRunner, GameConfig
from src.llmchess_simple.llm_opponent import LLMOpponent
from src.llmchess_simple.user_opponent import UserOpponent
from src.llmchess_simple.prompting import PromptConfig


def load_json(path: str) -> Dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def collect_config_files(spec: str) -> List[str]:
    files: List[str] = []
    parts = [p.strip() for p in spec.split(',') if p.strip()]
    for p in parts:
        if any(ch in p for ch in ['*', '?', '[']):
            files.extend(glob.glob(p))
        elif os.path.isdir(p):
            files.extend(glob.glob(os.path.join(p, '*.json')))
        elif os.path.isfile(p):
            files.append(p)
    return sorted(set(files))


def _parse_log_level(name: str | None) -> int:
    name = (name or "INFO").upper()
    return getattr(logging, name, logging.INFO)


def build_configs_from_dict(d: Dict):
    # Defaults
    model = d.get('model')
    if not model or not isinstance(model, str) or not model.strip():
        raise ValueError("Config must include a non-empty 'model' string (e.g., 'gpt-4o-mini').")
    provider = d.get('provider')
    provider_options = d.get('provider_options')
    opponent = d.get('opponent', 'llm')
    opponent_model = d.get('opponent_model')
    opponent_provider = d.get('opponent_provider') or provider
    opponent_provider_options = d.get('opponent_provider_options')
    opponent_name = d.get('opponent_name')
    games = d.get('games', 1)
    # Output directory is required and comes only from config
    out_dir = d.get('out_dir')
    if not isinstance(out_dir, str) or not out_dir.strip():
        raise ValueError("Config must include a non-empty 'out_dir' path (e.g., 'runs/test/').")
    # Color selection: prefer 'color' (may be 'white' | 'black' | 'both'),
    # with backward-compat fallback to 'llm_color'.
    color_cfg = (d.get('color') or d.get('llm_color') or 'white')
    max_plies = d.get('max_plies', 480)
    pgn_tail = d.get('pgn_tail', 20)
    verbose_llm = d.get('verbose_llm', False)
    # Mode fixed to sequential (legacy values ignored)
    mode = 'sequential'

    prompt = d.get('prompt', {}) or {}
    prompt_mode = prompt.get('mode', 'plaintext')
    starting_context_enabled = prompt.get('starting_context_enabled', True)
    instruction_line = prompt.get('instruction_line', 'Provide only your best legal move in SAN.')
    instruction_template = prompt.get('instructions_template')
    opponent_prompt = d.get('opponent_prompt', {}) or {}
    opp_prompt_cfg = None
    if opponent_prompt:
        opp_prompt_mode = opponent_prompt.get('mode', prompt_mode)
        opp_starting_context_enabled = opponent_prompt.get('starting_context_enabled', starting_context_enabled)
        opp_instruction_line = opponent_prompt.get('instruction_line', instruction_line)
        opp_instruction_template = opponent_prompt.get('instructions_template', instruction_template)
        opp_prompt_cfg = PromptConfig(mode=opp_prompt_mode, starting_context_enabled=opp_starting_context_enabled, instruction_line=opp_instruction_line, extra_instructions=opp_instruction_template)

    # Conversation/history logs will be placed under the run's output directory
    conv_every = True

    pcfg = PromptConfig(mode=prompt_mode, starting_context_enabled=starting_context_enabled, instruction_line=instruction_line, extra_instructions=instruction_template)
    # Always enable console game log and per-turn conversation/history logging.
    gcfg = GameConfig(max_plies=int(max_plies), pgn_tail_plies=int(pgn_tail), verbose_llm=bool(verbose_llm), conversation_log_path=None, conversation_log_every_turn=bool(conv_every), color=str(color_cfg if color_cfg != 'both' else 'white').lower(), prompt_cfg=pcfg, opponent_prompt_cfg=opp_prompt_cfg, game_log=True, provider=provider, provider_options=provider_options, opponent_provider_options=opponent_provider_options)

    if opponent not in ('llm', 'user'):
        raise ValueError("Unsupported opponent. Use 'llm' or 'user'.")
    if opponent == 'llm' and (not opponent_model or not str(opponent_model).strip()):
        raise ValueError("When opponent='llm', provide a non-empty 'opponent_model'.")

    return {
        'model': model,
        'provider': provider,
        'opponent_model': opponent_model,
        'opponent_provider': opponent_provider,
        'opponent_provider_options': opponent_provider_options,
        'opponent_name': opponent_name,
        'opponent': opponent,
        'out_dir': out_dir,
        'games': games,
        'gcfg': gcfg,
        'color': str(color_cfg).lower(),

    }


def _override_output_paths(gcfg: GameConfig, config_name: str, base_out_dir: str | None, force_every_turn: bool = False):
    """If base_out_dir is provided, place logs directly under that directory."""
    if not base_out_dir:
        return gcfg
    cfg_dir = base_out_dir
    os.makedirs(cfg_dir, exist_ok=True)
    gcfg.conversation_log_path = cfg_dir
    if force_every_turn:
        gcfg.conversation_log_every_turn = True
    return gcfg


def run_sequential(cfg_entry: Dict, config_name: str, jsonl_f, base_out_dir: str | None):
    model = cfg_entry['model']
    provider = cfg_entry.get('provider')
    opponent = cfg_entry['opponent']
    opponent_model = cfg_entry.get('opponent_model')
    opponent_provider = cfg_entry.get('opponent_provider') or provider
    opponent_name = cfg_entry.get('opponent_name')
    games = cfg_entry['games']
    color_cfg = str(cfg_entry.get('color', 'white')).lower()
    gcfg: GameConfig = cfg_entry['gcfg']
    
    base_gcfg = _override_output_paths(gcfg, config_name, base_out_dir, force_every_turn=True)

    # Determine iteration plan
    if color_cfg == 'both':
        total = games * 2
        def color_for_index_str(k: int) -> str:
            return 'white' if k < games else 'black'  # first half white, second half black
    else:
        total = games
        color_str = 'white' if color_cfg == 'white' else 'black'
        def color_for_index_str(k: int, _c=color_str) -> str:
            return _c

    all_metrics = []
    for i in range(total):
        # Clone per game and make output unique
        gcfg_i = copy.deepcopy(base_gcfg)
        gcfg_i.color = color_for_index_str(i)
        gcfg_i.provider = provider or gcfg_i.provider
        p = gcfg_i.conversation_log_path
        if p:
            try:
                root, ext = os.path.splitext(p)
                is_dir_like = os.path.isdir(p) or (ext == "")
                if is_dir_like:
                    subdir = os.path.join(p, f"g{i+1:03d}")
                    os.makedirs(subdir, exist_ok=True)
                    gcfg_i.conversation_log_path = subdir
                else:
                    base = os.path.basename(p)
                    name, ext = os.path.splitext(base)
                    new_base = f"{name}_g{i+1:03d}{ext or '.json'}"
                    gcfg_i.conversation_log_path = os.path.join(os.path.dirname(p), new_base)
            except Exception:
                pass
        if opponent == 'llm':
            if not opponent_model:
                raise ValueError("opponent_model is required when opponent='llm'.")
            opp_cfg = gcfg_i.opponent_prompt_cfg or gcfg_i.prompt_cfg
            opp = LLMOpponent(model=opponent_model, provider=opponent_provider, prompt_cfg=opp_cfg, name=opponent_name)
        elif opponent == 'user':
            opp = UserOpponent()
        else:
            raise ValueError("Unsupported opponent. Use 'llm' or 'user'.")
        runner = GameRunner(model=model, opponent=opp, cfg=gcfg_i)
        res = runner.play()
        m = runner.summary()
        m['config'] = config_name
        m['game_index'] = i
        all_metrics.append(m)
        print(f"[{config_name} Game {i+1}] result={res} reason={m['termination_reason']} plies={m['plies_total']}")
        if jsonl_f:
            jsonl_f.write(json.dumps(m) + '\n')
            jsonl_f.flush()
        opp.close()
    return all_metrics


def main():
    ap = argparse.ArgumentParser(description='Run many games by sweeping over JSON config files.')
    ap.add_argument('--configs', required=True, help='Comma-separated list of config paths, directories, or glob patterns (e.g., configs/*.json)')
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    log = logging.getLogger('run_many')

    files = collect_config_files(args.configs)
    if not files:
        log.error('No config files found for spec: %s', args.configs)
        sys.exit(1)

    grand_metrics = []
    t0 = time.time()

    for path in files:
        try:
            d = load_json(path)
        except Exception as e:
            log.error('Failed to read %s: %s', path, e)
            continue
        entry = build_configs_from_dict(d)
        # Effective log level comes from config (key: log_level), defaults to INFO
        eff_log_level_name = (d.get('log_level') or 'INFO')
        logging.getLogger().setLevel(_parse_log_level(eff_log_level_name))
        config_name = os.path.basename(path)
        # Determine out dir strictly from config (no defaults)
        base_out_dir = entry['out_dir']
        os.makedirs(base_out_dir, exist_ok=True)

        # Per-config JSONL file under the config-provided out_dir
        jsonl_path = os.path.join(base_out_dir, 'results.jsonl')
        jsonl_f = open(jsonl_path, 'a', encoding='utf-8') if jsonl_path else None
        metrics = run_sequential(entry, config_name, jsonl_f, base_out_dir)
        grand_metrics.extend(metrics)

        if jsonl_f:
            jsonl_f.close()

    # Aggregate overall
    results = [m.get('result','*') for m in grand_metrics]
    w = results.count('1-0'); l = results.count('0-1'); d = results.count('1/2-1/2')
    legal_rates = [m.get('llm_legal_rate', 0) for m in grand_metrics]
    legal_rates = [x for x in legal_rates if isinstance(x, (int, float))]
    avg_legal = statistics.mean(legal_rates) if legal_rates else 0
    avg_plies = statistics.mean([m.get('plies_total',0) for m in grand_metrics]) if grand_metrics else 0
    avg_latency = statistics.mean([m.get('latency_ms_avg',0) for m in grand_metrics]) if grand_metrics else 0

    print('\nGrand summary:')
    print(f"Configs: {len(files)}  Games: {len(grand_metrics)}  W={w} D={d} L={l}")
    print(f"Avg plies: {avg_plies:.1f}")
    print(f"Avg legal rate: {avg_legal*100:.2f}%")
    print(f"Avg LLM latency (ms): {avg_latency:.1f}")
    print(f"Wall time: {time.time()-t0:.1f}s")
    print("Outputs written under each config's 'out_dir' path.")

if __name__ == '__main__':
    main()
