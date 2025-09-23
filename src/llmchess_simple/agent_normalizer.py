"""
Agent-backed normalizer for raw LLM replies to chess moves.

Flow:
1) Quick regex to extract UCI from free-form text.
2) If not found and LLMCHESS_USE_GUARD_AGENT != "0", ask a tiny guard Agent (Agents SDK) to return UCI or NONE.
3) Fallback: first word-like token.

Returns lowercase UCI (with promotion letter) when possible; otherwise a best-effort token or empty string.

"""
from __future__ import annotations
import asyncio, logging, re
from agents import Agent, Runner, ModelSettings
from .config import SETTINGS

log = logging.getLogger("agent_normalizer") 

USE_GUARD_AGENT = SETTINGS.use_guard_agent

INSTRUCTIONS = (
    "You receive a raw reply.\n"
    "Ensure it is a chess move and avoid any other text.\n"
    "Output ONLY the move in UCI (lowercase, include promotion letter if any). If no move is present, output the single word NONE."
)

move_guard = Agent(
    name="MoveGuard",
    instructions=INSTRUCTIONS,
    model_settings=ModelSettings(temperature=0.0),
)

async def _agent_suggest(raw_reply: str) -> str:
    user = f"RAW REPLY: {raw_reply}\nReturn only the move in UCI or NONE:"
    result = await Runner.run(move_guard, user)
    return (result.final_output or "").strip()

UCI_RE = re.compile(r"\b([a-h][1-8][a-h][1-8][qrbnQRBN]?)\b")

def _quick_regex(raw: str) -> str | None:
    m = UCI_RE.search(raw)
    if m:
        return m.group(1).lower()
    return None

async def normalize_with_agent(raw_reply: str) -> str:
    """Simplified normalization flow.

    1. Try fast regex for UCI in raw reply.
    2. If found and legal, return.
    3. If guard agent enabled, ask it for a UCI candidate.
    4. Fallback: pick first token that looks like a move (letters/numbers) else NONE.
    """
    # Step 1: direct UCI pattern
    cand = _quick_regex(raw_reply)
    if cand:
        return cand

    agent_uci = None
    if USE_GUARD_AGENT:
        try:
            agent_uci = await _agent_suggest(raw_reply)
            agent_uci = (agent_uci or "").split()[0].strip().lower()
        except Exception:
            log.exception("Guard agent failed")

    if agent_uci and agent_uci != "none":
        return agent_uci

    # Fallback heuristic: first word-like token
    tokens = re.findall(r"[A-Za-z0-9=+-]+", raw_reply)
    return tokens[0].lower() if tokens else ""
