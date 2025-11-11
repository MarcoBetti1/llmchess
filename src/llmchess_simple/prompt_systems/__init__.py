from __future__ import annotations

from typing import Dict, Type

from .base import PromptSystem
from .legal_move_system_simple import LegalMoveSystemSimple
from .standard import StandardPromptSystem

_PROMPT_SYSTEMS: Dict[str, Type[PromptSystem]] = {
    StandardPromptSystem.name: StandardPromptSystem,
    "default": StandardPromptSystem,
    LegalMoveSystemSimple.name: LegalMoveSystemSimple,
}


def create_prompt_system(name: str | None) -> PromptSystem:
    key = (name or "standard").lower()
    cls = _PROMPT_SYSTEMS.get(key, StandardPromptSystem)
    return cls()
