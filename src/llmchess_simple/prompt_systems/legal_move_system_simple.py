from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

from ..agent_normalizer import normalize_with_agent
from ..agent_normalizer_yesno import normalize_yes_no_with_agent
from .base import PromptSystem, PromptSystemResult, PromptStage

if TYPE_CHECKING:  # pragma: no cover
    from src.llmchess_simple.game import GameRunner

log = logging.getLogger("prompt_system.legal_move_simple")


class LegalMoveSystemSimple(PromptSystem):
    """Two-step prompting system that double-checks legality of suggested moves."""

    name = "legal-move-system-simple"

    def __init__(self, max_attempts: int = 3) -> None:
        super().__init__()
        self.max_attempts = max_attempts
        self._phase: str = "proposal"
        self._attempts: int = 0
        self._illegal_moves: List[str] = []
        self._pending_candidate_raw: Optional[str] = None
        self._pending_candidate_move: Optional[str] = None

    # Lifecycle ------------------------------------------------------------
    def begin_turn(self, runner: "GameRunner") -> None:  # type: ignore[name-defined]
        super().begin_turn(runner)
        self._phase = "proposal"
        self._attempts = 0
        self._illegal_moves = []
        self._pending_candidate_raw = None
        self._pending_candidate_move = None

    def reset(self) -> None:
        super().reset()
        self._phase = "proposal"
        self._attempts = 0
        self._illegal_moves = []
        self._pending_candidate_raw = None
        self._pending_candidate_move = None

    # Core interaction -----------------------------------------------------
    def has_pending_followup(self) -> bool:
        return self._phase == "check"

    def build_messages(self, runner: "GameRunner") -> List[Dict[str, str]]:  # type: ignore[name-defined]
        if self._phase == "proposal":
            extra_lines: List[str] = []
            if self._attempts > 0:
                extra_lines.append(f"Attempt {self._attempts + 1} of {self.max_attempts}.")
            if self._illegal_moves:
                illegal = ", ".join(self._illegal_moves)
                extra_lines.append(f"Previous illegal attempts: {illegal}.")
                extra_lines.append("Those moves were illegal. Suggest a different legal move.")
            return runner._build_move_request_messages(extra_lines=extra_lines)  # pylint: disable=protected-access
        if not self._pending_candidate_move:
            # Safety: if we somehow reach check phase with no candidate, fallback to proposal prompt.
            log.warning("Check phase without candidate; reverting to proposal prompt.")
            self._phase = "proposal"
            return runner._build_move_request_messages()  # pylint: disable=protected-access
        return runner._build_legality_check_messages(self._pending_candidate_move, self._attempts + 1)  # pylint: disable=protected-access

    async def _extract_candidate(self, raw: str) -> str:
        try:
            return await normalize_with_agent(raw)
        except Exception:  # pragma: no cover - defensive
            log.exception("Failed to extract candidate move")
            return ""

    async def _classify_legality(self, raw: str) -> str:
        try:
            return await normalize_yes_no_with_agent(raw)
        except Exception:  # pragma: no cover - defensive
            log.exception("Failed to classify legality reply")
            return "unknown"

    def process_response(
        self, runner: "GameRunner", raw: str, messages: List[Dict[str, str]]
    ) -> PromptSystemResult:
        system, user = self._extract_prompts(messages)
        stage_name = "proposal" if self._phase == "proposal" else "check"
        stage = PromptStage(stage=stage_name, system=system, user=user, assistant=raw)
        self.record_stage(stage)

        if self._phase == "proposal":
            candidate = asyncio.run(self._extract_candidate(raw))
            self._pending_candidate_raw = raw
            self._pending_candidate_move = candidate
            metadata = {
                "candidate_move": candidate,
                "proposal_attempt": self._attempts + 1,
            }
            if not candidate:
                # No parseable move; hand raw back to validator immediately.
                metadata["candidate_empty"] = True
                return PromptSystemResult(completed=True, raw_for_move=raw, metadata=metadata)
            self._phase = "check"
            return PromptSystemResult(completed=False, metadata=metadata)

        # Check phase -------------------------------------------------------
        decision = asyncio.run(self._classify_legality(raw))
        metadata = {
            "candidate_move": self._pending_candidate_move,
            "legality_response": raw,
            "legality_decision": decision,
            "proposal_attempt": self._attempts + 1,
        }

        if decision == "yes":
            metadata["confirmed_legal"] = True
            snapshot_raw = self._pending_candidate_raw or raw
            self._phase = "proposal"
            return PromptSystemResult(completed=True, raw_for_move=snapshot_raw, metadata=metadata)

        # Decision is no/unknown -------------------------------------------
        move_label = self._pending_candidate_move or (self._pending_candidate_raw or "")
        if move_label:
            self._illegal_moves.append(move_label)
        metadata["confirmed_legal"] = False
        if decision == "unknown":
            metadata["uncertain_check"] = True

        self._attempts += 1
        limit_reached = self._attempts >= self.max_attempts
        metadata["max_attempts_reached"] = limit_reached

        if limit_reached:
            metadata["forced_due_to_limit"] = True
            snapshot_raw = self._pending_candidate_raw or raw
            self._phase = "proposal"
            return PromptSystemResult(completed=True, raw_for_move=snapshot_raw, metadata=metadata)

        # Otherwise retry proposal -----------------------------------------
        self._phase = "proposal"
        self._pending_candidate_raw = None
        self._pending_candidate_move = None
        metadata["retry"] = True
        return PromptSystemResult(completed=False, metadata=metadata)
