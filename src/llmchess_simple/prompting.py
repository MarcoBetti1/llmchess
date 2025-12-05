"""
Prompt builders and config for LLM move requests using a modular template.

Callers supply system instructions and a template string with placeholders
that are substituted per turn.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

DEFAULT_SAN_SYSTEM = "You are a strong chess player. When asked for a move, provide only the best legal move in SAN."
DEFAULT_SAN_TEMPLATE = """Position (FEN): {FEN}
Respond with only your best legal move in SAN."""

DEFAULT_UCI_SYSTEM = "You are a chess engine. Respond with exactly one legal move in long algebraic UCI (e.g., e2e4). Return only the move."
DEFAULT_UCI_TEMPLATE = """Board FEN: {FEN}
Move history (SAN): {SAN_HISTORY}
Side to move: {SIDE_TO_MOVE}
Reply with only the best legal move in UCI (e.g., e2e4, g7g8q)."""

DEFAULT_FEN_SYSTEM = "You generate the resulting board position as a FEN after making your move. Output only that FEN."
DEFAULT_FEN_TEMPLATE = """Board before your move (FEN): {FEN}
Move history (SAN): {SAN_HISTORY}
You are playing as {SIDE_TO_MOVE}. Make the best legal move, then return ONLY the resulting board FEN after your move."""

# Backwards-compatible aliases
DEFAULT_SYSTEM_INSTRUCTIONS = DEFAULT_SAN_SYSTEM
DEFAULT_TEMPLATE = DEFAULT_SAN_TEMPLATE


@dataclass
class PromptConfig:
    """Configuration for shaping move prompts using a custom template."""

    system_instructions: str = DEFAULT_SAN_SYSTEM
    template: str = DEFAULT_SAN_TEMPLATE
    expected_notation: str = "san"  # "san" | "uci" | "fen"


def render_custom_prompt(template: str, values: Dict[str, str]) -> str:
    """Replace known placeholders in the template. Unknown tokens are left intact."""
    rendered = template or ""
    for key, val in values.items():
        rendered = rendered.replace(f"{{{key}}}", val)
    return rendered
