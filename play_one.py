import argparse
import logging
from datetime import datetime
from src.llmchess_simple.game import GameRunner, GameConfig
from src.llmchess_simple.engine_opponent import EngineOpponent
from src.llmchess_simple.random_opponent import RandomOpponent

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5")
    ap.add_argument("--depth", type=int, default=6, help="Engine search depth (ignored if --movetime provided)")
    ap.add_argument("--movetime", type=int, default=None, help="Engine movetime in ms (overrides depth if set)")
    ap.add_argument("--max-plies", type=int, default=240)
    ap.add_argument("--pgn-tail", type=int, default=20, help="How many recent plies to include in prompt context (standard mode only)")
    ap.add_argument("--pgn-out", default=None, help="Optional path to write PGN")
    ap.add_argument("--log-level", default="INFO", help="Python logging level")
    ap.add_argument("--verbose-llm", action="store_true", help="Log raw LLM replies")
    ap.add_argument("--conversation", action="store_true", help="Enable conversation mode (no FEN sent; pure chat history)")
    ap.add_argument("--opponent", choices=["engine", "random"], default="engine", help="Opponent type")
    args = ap.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    log = logging.getLogger("play_one")

    if args.opponent == "random":
        opp = RandomOpponent()
    else:
        opp = EngineOpponent(depth=args.depth, movetime_ms=args.movetime)
    cfg = GameConfig(max_plies=args.max_plies, pgn_tail_plies=args.pgn_tail, verbose_llm=args.verbose_llm, conversation_mode=args.conversation)
    runner = GameRunner(model=args.model, opponent=opp, cfg=cfg)
    mode_label = "conversation" if args.conversation else "standard"
    log.info("Starting single game (%s mode): model=%s vs %s depth=%s movetime=%s", mode_label, args.model, args.opponent, args.depth, args.movetime)
    result = runner.play()
    metrics = runner.metrics()

    print("Result:", result)
    print("Termination:", runner.termination_reason)
    print("Metrics:", metrics)
    print("PGN:\n", runner.ref.pgn())
    if args.conversation:
        print("Conversation messages:")
        for m in runner.chat_messages:
            print(f"  {m['role']}: {m['content']}")

    if args.pgn_out:
        with open(args.pgn_out, "w", encoding="utf-8") as f:
            f.write(runner.ref.pgn())
        log.info("Wrote PGN to %s", args.pgn_out)

    opp.close()
