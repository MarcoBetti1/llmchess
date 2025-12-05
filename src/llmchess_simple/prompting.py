"""
Prompt builders and config for LLM move requests using a modular template.

Callers supply system instructions and a template string with placeholders
that are substituted per turn.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

DEFAULT_SYSTEM_INSTRUCTIONS = "You are a strong chess player. When asked for a move, provide only the best legal move in SAN."
DEFAULT_TEMPLATE = """Position (FEN): {FEN}
Respond with only your best legal move in SAN."""


@dataclass
class PromptConfig:
    """Configuration for shaping move prompts using a custom template."""

    mode: str = "custom"  # retained for logging/metadata only
    system_instructions: str = DEFAULT_SYSTEM_INSTRUCTIONS
    template: str = DEFAULT_TEMPLATE
    starting_context_enabled: bool = True


def render_custom_prompt(template: str, values: Dict[str, str]) -> str:
    """Replace known placeholders in the template. Unknown tokens are left intact."""
    rendered = template or ""
    for key, val in values.items():
        rendered = rendered.replace(f"{{{key}}}", val)
    return rendered
