from __future__ import annotations
"""LLM-backed opponent for model-vs-model evaluation."""
import logging
from dataclasses import dataclass
from typing import Optional

import chess

from .llm_client import ask_for_best_move_conversation
from .llm_play import build_prompt_messages_for_board, process_llm_raw_move
from .prompting import PromptConfig


@dataclass
class LLMOpponent:
    model: str
    provider: Optional[str] = None
    provider_options: Optional[dict] = None
    prompt_cfg: Optional[PromptConfig] = None
    name: Optional[str] = None

    def label(self) -> str:
        return self.name or self.model

    def choose_llm(self, board: chess.Board, apply_uci_fn, pgn_tail_plies: int, salvage_with_validator: bool, verbose_llm: bool, log: logging.Logger, prompt_cfg: Optional[PromptConfig] = None, provider_options: Optional[dict] = None):
        """Generate a move using the configured LLM and apply it via the provided callback."""
        cfg = prompt_cfg or self.prompt_cfg or PromptConfig()
        side = "white" if board.turn == chess.WHITE else "black"
        is_starting = side == "white" and len(board.move_stack) == 0
        messages = build_prompt_messages_for_board(
            board=board,
            side=side,
            prompt_cfg=cfg,
            pgn_tail_plies=pgn_tail_plies,
            is_starting=is_starting,
        )
        raw = ask_for_best_move_conversation(messages, model=self.model, provider=self.provider, provider_options=provider_options or self.provider_options)
        meta_extra = {
            "mode": "opponent_llm",
            "prompt": messages[-1]["content"] if messages else "",
            "system": messages[0]["content"] if messages else "",
            "prompt_mode": cfg.mode,
            "prompt_template": getattr(cfg, "template", None),
            "model": self.model,
        }
        ok, uci, san, ms, meta, _ = process_llm_raw_move(
            raw,
            board.fen(),
            apply_uci_fn=apply_uci_fn,
            salvage_with_validator=salvage_with_validator,
            verbose_llm=verbose_llm,
            log=log,
            meta_extra=meta_extra,
        )
        meta["model"] = self.model
        meta["provider"] = self.provider
        meta["latency_ms"] = ms
        return ok, uci, san, meta

    def close(self):
        # Nothing to release for API-based opponents
        return
