import argparse
import json
import logging
from src.llmchess_simple.game import GameRunner, GameConfig
from src.llmchess_simple.engine_opponent import EngineOpponent
from src.llmchess_simple.random_opponent import RandomOpponent
from src.llmchess_simple.prompting import PromptConfig


def load_json_config(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.getLogger("play_one").error("Failed to read config %s: %s", path, e)
        return {}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None, help="Optional JSON config file to load defaults from.")
    ap.add_argument("--model", default=None, help="Target model name (overrides config)")
    ap.add_argument("--opponent", choices=["engine", "random"], default=None, help="Opponent type")
    ap.add_argument("--depth", type=int, default=None, help="Engine search depth (ignored if --movetime provided)")
    ap.add_argument("--movetime", type=int, default=None, help="Engine movetime in ms (overrides depth if set)")
    ap.add_argument("--engine", default=None, help="Engine name to use (Stockfish only for now). Path is read from env.")
    ap.add_argument("--llm-color", choices=["white", "black"], default=None, help="Which side the LLM plays")
    ap.add_argument("--max-plies", type=int, default=None)
    ap.add_argument("--max-illegal", type=int, default=None, help="Terminate after this many illegal LLM moves (1 means immediate)")
    ap.add_argument("--pgn-tail", type=int, default=None, help="How many recent plies to include in prompts (used in FEN mode as PGN tail; still used internally)")
    ap.add_argument("--verbose-llm", action="store_true", help="Log raw LLM replies")
    ap.add_argument("--conversation", action="store_true", help="Enable legacy conversation mode (bypasses modular prompting)")
    # Prompting configuration
    ap.add_argument("--prompt-mode", choices=["plaintext", "fen"], default=None, help="Prompting style for standard mode")
    ap.add_argument("--no-starting-context", action="store_true", help="Disable explicit first-move starting context line")
    ap.add_argument("--instruction-line", default=None, help="Override instruction line appended to the prompt")
    # Conversation logging options
    ap.add_argument("--conv-log", default=None, help="Path to JSON file or directory for conversation dumps")
    ap.add_argument("--conv-log-every-turn", action="store_true", help="Dump conversation JSON after every move")
    # Misc
    ap.add_argument("--pgn-out", default=None, help="Optional path to write PGN at end")
    ap.add_argument("--log-level", default=None, help="Python logging level (e.g., INFO, DEBUG)")

    args = ap.parse_args()

    # Load config defaults
    cfg_dict = load_json_config(args.config) if args.config else {}

    # Resolve values with precedence: CLI arg if provided -> config -> default
    def pick(*keys, default=None):
        for k in keys:
            v = getattr(args, k, None)
            if v is not None:
                return v
            if k in cfg_dict and cfg_dict[k] is not None:
                return cfg_dict[k]
        return default

    # Logging setup
    log_level = pick("log_level", default="INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("play_one")

    model = pick("model", default=None)
    if not model:
        raise ValueError("Model is required. Provide --model or set 'model' in the JSON config.")
    opponent_type = pick("opponent", default="engine")
    depth = pick("depth", default=6)
    movetime = pick("movetime", default=None)
    engine = pick("engine", default=(cfg_dict.get("engine") if isinstance(cfg_dict.get("engine"), str) else "Stockfish"))
    llm_color = pick("llm_color", default="white")
    max_plies = pick("max_plies", default=240)
    max_illegal = pick("max_illegal", default=1)
    pgn_tail = pick("pgn_tail", default=20)
    verbose_llm = args.verbose_llm or bool(cfg_dict.get("verbose_llm", False))
    conversation_mode = args.conversation or bool(cfg_dict.get("conversation_mode", False))

    # Prompting
    prompt_mode = pick("prompt_mode", default=(cfg_dict.get("prompt", {}) or {}).get("mode", "plaintext"))
    starting_context_enabled = not args.no_starting_context if args.no_starting_context else (cfg_dict.get("prompt", {}).get("starting_context_enabled", True))
    instruction_line = pick("instruction_line", default=(cfg_dict.get("prompt", {}) or {}).get("instruction_line", "Provide only your best legal move in SAN."))

    # Conversation logging
    conv_cfg = cfg_dict.get("conversation_log", {}) if isinstance(cfg_dict.get("conversation_log"), dict) else {}
    conv_log_path = pick("conv_log", default=conv_cfg.get("path"))
    conv_every_turn = args.conv_log_every_turn or bool(conv_cfg.get("every_turn", False))

    # Opponent
    if opponent_type == "random":
        opp = RandomOpponent()
    else:
        if engine and str(engine).lower() != "stockfish":
            raise ValueError(f"Unsupported engine '{engine}'. Only 'Stockfish' is supported.")
        opp = EngineOpponent(depth=int(depth) if depth is not None else None, movetime_ms=int(movetime) if movetime is not None else None, engine_path=None)

    # Build PromptConfig and GameConfig
    pcfg = PromptConfig(mode=prompt_mode, starting_context_enabled=starting_context_enabled, instruction_line=instruction_line)
    gcfg = GameConfig(
        max_plies=int(max_plies),
        pgn_tail_plies=int(pgn_tail),
        verbose_llm=verbose_llm,
        conversation_mode=conversation_mode,
        max_illegal_moves=int(max_illegal),
        conversation_log_path=conv_log_path,
        conversation_log_every_turn=conv_every_turn,
        llm_is_white=(llm_color == "white"),
        prompt_cfg=pcfg,
    )

    runner = GameRunner(model=model, opponent=opp, cfg=gcfg)
    mode_label = "conversation" if conversation_mode else f"standard:{prompt_mode}"
    log.info("Starting game: model=%s vs %s depth=%s movetime=%s engine=%s side=%s mode=%s", model, opponent_type, depth, movetime, engine, llm_color, mode_label)
    result = runner.play()
    metrics = runner.metrics()

    print("Result:", result)
    print("Termination:", runner.termination_reason)
    print("Metrics:", metrics)
    print("PGN:\n", runner.ref.pgn())

    if gcfg.conversation_mode:
        print("Conversation messages:")
        for m in runner.chat_messages:
            print(f"  {m['role']}: {m['content']}")

    if args.pgn_out:
        with open(args.pgn_out, "w", encoding="utf-8") as f:
            f.write(runner.ref.pgn())
        log.info("Wrote PGN to %s", args.pgn_out)

    opp.close()
