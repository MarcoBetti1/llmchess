"""
Prompt system abstractions for orchestrating multi-stage LLM interactions per move.

Each prompt system coordinates one LLM-controlled turn. Implementations are
responsible for producing the next message to send, tracking intermediate
responses, and determining when a candidate move is ready for validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle protection for type hints
    from src.llmchess_simple.game import GameRunner


@dataclass
class PromptStage:
    """Represents a single prompt/response exchange within a turn."""

    stage: str
    system: str
    user: str
    assistant: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "stage": self.stage,
            "system": self.system,
            "user": self.user,
            "assistant": self.assistant,
        }


@dataclass
class PromptSystemResult:
    """Return value for PromptSystem.process_response."""

    completed: bool
    raw_for_move: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PromptSystem:
    """Interface for coordinating prompts across one LLM turn."""

    name: str = "standard"

    def __init__(self) -> None:
        self._stages: List[PromptStage] = []

    # -- lifecycle ---------------------------------------------------------
    def begin_turn(self, runner: "GameRunner") -> None:
        """Prepare system state at the start of a new turn."""
        self.reset()

    def reset(self) -> None:
        """Reset internal stage history and any custom state."""
        self._stages.clear()

    # -- interaction -------------------------------------------------------
    def has_pending_followup(self) -> bool:
        """Return True if the system expects additional LLM turns this move."""
        return False

    def build_messages(self, runner: "GameRunner") -> List[Dict[str, str]]:
        """Produce the next chat messages to send to the LLM."""
        raise NotImplementedError

    def process_response(
        self, runner: "GameRunner", raw: str, messages: List[Dict[str, str]]
    ) -> PromptSystemResult:
        """Process an LLM response and decide whether the turn is complete."""
        raise NotImplementedError

    # -- book-keeping ------------------------------------------------------
    def record_stage(self, stage: PromptStage) -> None:
        self._stages.append(stage)

    def get_stages(self) -> List[PromptStage]:
        return list(self._stages)

    # Utility for children -------------------------------------------------
    @staticmethod
    def _extract_prompts(messages: List[Dict[str, str]]) -> tuple[str, str]:
        if not messages:
            return "", ""
        system = ""
        user = ""
        for msg in messages:
            role = msg.get("role")
            if role == "system" and not system:
                system = msg.get("content", "")
            elif role == "user":
                user = msg.get("content", "")
        return system, user
