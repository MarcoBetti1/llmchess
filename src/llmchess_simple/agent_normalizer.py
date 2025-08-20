from __future__ import annotations
import asyncio, logging, os
try:
    from agents import Agent, Runner, ModelSettings
except Exception:  # pragma: no cover
    from openai_agents import Agent, Runner, ModelSettings  # type: ignore
from .move_validator import normalize_move
import chess

log = logging.getLogger("agent_normalizer")

USE_GUARD_AGENT = os.environ.get("LLMCHESS_USE_GUARD_AGENT", "1") != "0"

INSTRUCTIONS = (
    "You will receive a chess position in FEN and a raw reply from a different model.\n"
    "Goal: extract exactly ONE legal move for the given position.\n"
    "Respond ONLY with the move in pure UCI (e.g., e2e4, g1f3, e7e8q). No commentary.\n"
    "If the raw reply contains multiple moves, pick the first legal one. If none appear, attempt to infer the intended move."
)

move_guard = Agent(
    name="MoveGuard",
    instructions=INSTRUCTIONS,
    model_settings=ModelSettings(temperature=0.0)
)

async def _agent_suggest(fen: str, raw_reply: str) -> str:
    user = f"FEN: {fen}\nRAW REPLY: {raw_reply}\nReturn only UCI:"
    result = await Runner.run(move_guard, user)
    return (result.final_output or "").strip()

async def normalize_with_agent(fen: str, raw_reply: str) -> str:
    """Return a legal UCI move string or raise RuntimeError.

    Pipeline:
      1. (Optional) Guard agent attempts to produce UCI.
      2. Validate agent output with normalize_move.
      3. If invalid, run normalize_move on raw LLM reply directly.
      4. If still invalid, raise.
    """
    board = chess.Board(fen)
    agent_uci = None
    if USE_GUARD_AGENT:
        try:
            agent_uci = await _agent_suggest(fen, raw_reply)
        except Exception:
            log.exception("Guard agent failed; continuing with raw fallback")

    # Step 2: validate agent output
    if agent_uci:
        v = normalize_move(agent_uci, fen)
        if v.get("ok"):
            return v["uci"]
        else:
            log.debug("Agent output not valid: %s (%s)", agent_uci, v.get("reason"))

    # Step 3: try full normalization on raw reply
    v2 = normalize_move(raw_reply, fen)
    if v2.get("ok"):
        return v2["uci"]

    # Final attempt: if we still have an agent candidate string, try to coerce common SAN -> UCI
    if agent_uci and len(agent_uci) <= 7:  # heuristic length filter
        v3 = normalize_move(agent_uci, fen)
        if v3.get("ok"):
            return v3["uci"]

    raise RuntimeError(f"Could not extract a legal move. Reason: {v2.get('reason')}")
