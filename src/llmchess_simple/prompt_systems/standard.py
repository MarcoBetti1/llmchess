from __future__ import annotations

from typing import Dict, List, TYPE_CHECKING

from .base import PromptSystem, PromptSystemResult, PromptStage

if TYPE_CHECKING:  # pragma: no cover
    from src.llmchess_simple.game import GameRunner


class StandardPromptSystem(PromptSystem):
    """Default single-shot prompting flow."""

    name = "standard"

    def build_messages(self, runner: "GameRunner") -> List[Dict[str, str]]:  # type: ignore[name-defined]
        self._last_messages = runner._build_move_request_messages()  # pylint: disable=protected-access
        return self._last_messages

    def process_response(
        self, runner: "GameRunner", raw: str, messages: List[Dict[str, str]]
    ) -> PromptSystemResult:
        system, user = self._extract_prompts(messages)
        stage = PromptStage(stage="proposal", system=system, user=user, assistant=raw)
        self.record_stage(stage)
        metadata = {
            "prompt": user,
            "system": system,
            "primary_response": raw,
        }
        return PromptSystemResult(completed=True, raw_for_move=raw, metadata=metadata)
