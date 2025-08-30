import argparse, json, logging, os, sys, glob, statistics, time, datetime
import copy
from typing import List, Dict

# Ensure project root added
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.llmchess_simple.game import GameRunner, GameConfig
from src.llmchess_simple.engine_opponent import EngineOpponent
from src.llmchess_simple.random_opponent import RandomOpponent
from src.llmchess_simple.prompting import PromptConfig
from src.llmchess_simple.batch_orchestrator import BatchOrchestrator


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


def build_configs_from_dict(d: Dict):
    # Defaults
    model = d.get('model', 'gpt-5')
    opponent = d.get('opponent', 'engine')
    depth = d.get('depth', 6)
    movetime = d.get('movetime')
    engine_path = d.get('engine_path')
    llm_color = d.get('llm_color', 'white')
    max_plies = d.get('max_plies', 240)
    max_illegal = d.get('max_illegal', 1)
    pgn_tail = d.get('pgn_tail', 20)
    verbose_llm = d.get('verbose_llm', False)
    game_log = d.get('game_log', False)
    conversation_mode = d.get('conversation_mode', False)
    # New unified mode switch: "parallel" | "batch" (required going forward)
    mode = str(d.get('mode', 'parallel')).strip().lower()
    if mode not in ('parallel', 'batch'):
        logging.getLogger('run_many').warning("Unknown mode '%s'; defaulting to 'parallel'", mode)
        mode = 'parallel'

    # Optional chunk size for batch jobs; if None, provider/env defaults apply
    games_per_batch = d.get('games_per_batch')

    prompt = d.get('prompt', {}) or {}
    prompt_mode = prompt.get('mode', 'plaintext')
    starting_context_enabled = prompt.get('starting_context_enabled', True)
    instruction_line = prompt.get('instruction_line', 'Provide only your best legal move in SAN.')

    conv = d.get('conversation_log', {}) or {}
    conv_path = conv.get('path')
    conv_every = conv.get('every_turn', False)

    pcfg = PromptConfig(mode=prompt_mode, starting_context_enabled=starting_context_enabled, instruction_line=instruction_line)
    gcfg = GameConfig(max_plies=int(max_plies), pgn_tail_plies=int(pgn_tail), verbose_llm=bool(verbose_llm), conversation_mode=bool(conversation_mode), max_illegal_moves=int(max_illegal), conversation_log_path=conv_path, conversation_log_every_turn=bool(conv_every), llm_is_white=(llm_color=='white'), prompt_cfg=pcfg, game_log=bool(game_log))

    return {
        'model': model,
        'opponent': opponent,
        'depth': depth,
        'movetime': movetime,
        'engine_path': engine_path,
        'games': int(d.get('games', 1)),
        # Unified execution mode
        'mode': mode,
        # Optional: chunk size for OpenAI Batches API
    'games_per_batch': (int(games_per_batch) if isinstance(games_per_batch, (int, float)) else None),
        'gcfg': gcfg,
    # No legacy fields supported going forward
    }


def _override_output_paths(gcfg: GameConfig, config_name: str, base_out_dir: str | None, force_every_turn: bool = False):
    """If base_out_dir is provided, place conversation + structured history under
    base_out_dir/<config_name_without_ext>/
    """
    if not base_out_dir:
        return gcfg
    sub = os.path.splitext(os.path.basename(config_name))[0]
    cfg_dir = os.path.join(base_out_dir, sub)
    os.makedirs(cfg_dir, exist_ok=True)
    gcfg.conversation_log_path = cfg_dir
    if force_every_turn:
        gcfg.conversation_log_every_turn = True
    return gcfg


def run_sequential(cfg_entry: Dict, config_name: str, jsonl_f, base_out_dir: str | None):
    model = cfg_entry['model']
    opponent = cfg_entry['opponent']
    depth = cfg_entry['depth']
    movetime = cfg_entry['movetime']
    engine_path = cfg_entry['engine_path']
    games = cfg_entry['games']
    gcfg: GameConfig = cfg_entry['gcfg']

    # Override output paths per config if requested
    base_gcfg = _override_output_paths(gcfg, config_name, base_out_dir, force_every_turn=True)

    all_metrics = []
    for i in range(games):
        # Clone per game and make output unique
        gcfg_i = copy.deepcopy(base_gcfg)
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
        if opponent == 'random':
            opp = RandomOpponent()
        else:
            # Keep sequential path consistent with batched path
            opp = EngineOpponent(depth=depth, movetime_ms=movetime, engine_path=engine_path)
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


def run_batched(cfg_entry: Dict, config_name: str, jsonl_f, base_out_dir: str | None, prefer_batches: bool | None = None, items_per_batch: int | None = None):
    model = cfg_entry['model']
    opponent = cfg_entry['opponent']
    depth = cfg_entry['depth']
    movetime = cfg_entry['movetime']
    engine_path = cfg_entry['engine_path']
    games = cfg_entry['games']
    gcfg: GameConfig = cfg_entry['gcfg']

    # Override output paths per config if requested
    gcfg = _override_output_paths(gcfg, config_name, base_out_dir, force_every_turn=True)

    # batch orchestrator == multi-game loop; prefer_batches decides transport (Batches API vs parallel /responses)
    orch = BatchOrchestrator(model=model, num_games=games, opponent=opponent, depth=depth, movetime_ms=movetime, engine_path=engine_path, base_cfg=gcfg, prefer_batches=prefer_batches, items_per_batch=items_per_batch)
    summaries = orch.run()
    all_metrics = []
    for i, m in enumerate(summaries):
        m['config'] = config_name
        m['game_index'] = i
        all_metrics.append(m)
        res = m.get('result', '*')
        print(f"[{config_name} Game {i+1}] result={res} reason={m.get('termination_reason')} plies={m.get('plies_total')}")
        if jsonl_f:
            jsonl_f.write(json.dumps(m) + '\n')
            jsonl_f.flush()
    return all_metrics


def main():
    ap = argparse.ArgumentParser(description='Run many games by sweeping over JSON config files.')
    ap.add_argument('--configs', required=True, help='Comma-separated list of config paths, directories, or glob patterns (e.g., configs/*.json)')
    # Unified mode switch (CLI). If omitted, config decides.
    ap.add_argument('--mode', choices=['parallel', 'batch'], help='Execution mode: parallel (responses API) or batch (OpenAI Batches API). Overrides config.')
    ap.add_argument('--games-per-batch', type=int, default=None, help='Chunk size for OpenAI Batches API (per cycle). Overrides config.')
    ap.add_argument('--out-jsonl', default=None, help='Path to write per-game metrics as JSONL')
    ap.add_argument('--out-dir', default=None, help='Base output directory to store logs per test run (defaults to runs/run_YYYYMMDD-HHMMSS)')
    ap.add_argument('--game-log', action='store_true', help='Enable console logging of each LLM/engine move to monitor progress')
    ap.add_argument('--log-level', default='INFO')
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    log = logging.getLogger('run_many')

    files = collect_config_files(args.configs)
    if not files:
        log.error('No config files found for spec: %s', args.configs)
        sys.exit(1)

    # Prepare base output directory
    base_out_dir = args.out_dir
    created_default_out = False
    if not base_out_dir:
        ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        base_out_dir = os.path.join(os.getcwd(), 'runs', f'run_{ts}')
        os.makedirs(base_out_dir, exist_ok=True)
        created_default_out = True
    else:
        os.makedirs(base_out_dir, exist_ok=True)

    # If no explicit JSONL, default to base_out_dir/results.jsonl
    jsonl_path = args.out_jsonl or os.path.join(base_out_dir, 'results.jsonl')
    jsonl_f = open(jsonl_path, 'a', encoding='utf-8') if jsonl_path else None

    grand_metrics = []
    t0 = time.time()

    for path in files:
        try:
            d = load_json(path)
        except Exception as e:
            log.error('Failed to read %s: %s', path, e)
            continue
        entry = build_configs_from_dict(d)
        # Apply CLI overrides
        if args.game_log:
            entry['gcfg'].game_log = True
        config_name = os.path.basename(path)
        # Determine mode precedence: CLI --mode > config.mode
        mode = args.mode if args.mode else entry.get('mode', 'parallel')

        if mode == 'batch':
            # In the new model, batch mode always uses the OpenAI Batches API transport
            prefer_batches = True
            # Allow CLI override for chunk size; else take from config; provider will fallback to env if None
            items_per_batch = args.games_per_batch if args.games_per_batch is not None else entry.get('games_per_batch')
            metrics = run_batched(entry, config_name, jsonl_f, base_out_dir, prefer_batches=prefer_batches, items_per_batch=items_per_batch)
        else:
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
    print(f"Outputs: {base_out_dir}")

if __name__ == '__main__':
    main()
