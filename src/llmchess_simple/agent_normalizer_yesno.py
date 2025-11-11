"""
Agent-backed yes/no classifier used by prompt systems that require legality confirmation.

Flow mirrors agent_normalizer but targets binary responses:
1. Fast heuristic check for common yes/no tokens.
2. Optional guard agent (shared settings flag) that must return YES or NO.
3. Fallback to "unknown" when classification fails.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Literal

from agents import Agent, Runner, ModelSettings

from .config import SETTINGS

log = logging.getLogger("agent_normalizer_yesno")

USE_GUARD_AGENT = SETTINGS.use_guard_agent

INSTRUCTIONS = (
    "You receive a raw reply.\n"
    "Output ONLY the single word YES if the answer indicates the move is legal,\n"
    "and the single word NO if it indicates the move is not legal.\n"
    "If you cannot determine the answer, return the single word UNKNOWN."
)

yes_no_guard = Agent(
    name="YesNoGuard",
    instructions=INSTRUCTIONS,
    model_settings=ModelSettings(temperature=0.0),
)

YES_RE = re.compile(r"\b(yes|yep|yeah|legal|it[\s-]?is|correct)\b", re.IGNORECASE)
NO_RE = re.compile(r"\b(no|nope|nah|illegal|not\s+legal|incorrect)\b", re.IGNORECASE)

ResponseLabel = Literal["yes", "no", "unknown"]


async def _agent_classify(raw_reply: str) -> ResponseLabel:
    user = (
        "RAW REPLY: "
        f"{raw_reply}\n"
        "Return only YES, NO, or UNKNOWN to indicate whether the original reply confirms the move is legal."
    )
    try:
        result = await Runner.run(yes_no_guard, user)
    except Exception:  # pragma: no cover - defensive logging
        log.exception("Guard agent classification failed")
        return "unknown"
    output = (result.final_output or "").strip().lower()
    if output in {"yes", "no"}:
        return output  # type: ignore[return-value]
    return "unknown"


def _heuristic(raw: str) -> ResponseLabel:
    if YES_RE.search(raw):
        return "yes"
    if NO_RE.search(raw):
        return "no"
    return "unknown"


async def normalize_yes_no_with_agent(raw_reply: str) -> ResponseLabel:
    """Classify a free-form answer into yes/no/unknown."""
    heuristic = _heuristic(raw_reply)
    if heuristic != "unknown":
        return heuristic
    if USE_GUARD_AGENT:
        agent_answer = await _agent_classify(raw_reply)
        if agent_answer != "unknown":
            return agent_answer
    return "unknown"


def classify_yes_no(raw_reply: str) -> ResponseLabel:
    """Convenience synchronous wrapper."""
    return asyncio.run(normalize_yes_no_with_agent(raw_reply))
