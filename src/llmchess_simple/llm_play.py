from __future__ import annotations
"""
Shared helpers for building prompts and processing LLM moves.

These utilities keep GameRunner and LLM-based opponents symmetric and
provider-agnostic.
"""
import logging
import time
from typing import Callable

import chess

from .move_validator import parse_expected_move, Notation
from .prompting import PromptConfig, render_custom_prompt


def annotated_history_from_board(board: chess.Board) -> str:
    """Return history as one move per line: 'White Pawn e4' / 'Black Knight f6'. No numbering."""
    lines: list[str] = []
    replay = chess.Board()
    for mv in board.move_stack:
        piece = replay.piece_at(mv.from_square)
        san = replay.san(mv)
        color = "White" if replay.turn == chess.WHITE else "Black"
        piece_name = chess.piece_name(piece.piece_type).capitalize() if piece else "Piece"
        lines.append(f"{color} {piece_name} {san}")
        replay.push(mv)
    return "\n".join(lines)


def pgn_tail_from_board(board: chess.Board, max_plies: int) -> str:
    """Produce a clean SAN move list without headers, truncated to the last max_plies."""
    if max_plies <= 0:
        return ""
    replay = chess.Board()  # start pos
    sans: list[str] = []
    for idx, mv in enumerate(board.move_stack):
        san = replay.san(mv)
        replay.push(mv)
        move_no = (idx // 2) + 1
        if idx % 2 == 0:  # white move, include move number
            sans.append(f"{move_no}. {san}")
        else:
            sans.append(san)
    tail = sans[-max_plies:]
    return " ".join(tail)


def build_prompt_messages_for_board(board: chess.Board, side: str, prompt_cfg: PromptConfig, pgn_tail_plies: int, is_starting: bool) -> list[dict]:
    """Construct prompt messages for the given board/side using the configured template."""
    history = annotated_history_from_board(board)
    fen = board.fen()
    san_history = pgn_tail_from_board(board, pgn_tail_plies) or "(none)"
    values = {
        "SIDE_TO_MOVE": side,
        "FEN": fen,
        "SAN_HISTORY": san_history,
        "PLAINTEXT_HISTORY": history or "(none)",
    }
    user_content = render_custom_prompt(prompt_cfg.template, values)
    # Optionally add starting context if desired and it's the first move
    # if is_starting and prompt_cfg.starting_context_enabled and side.lower() == "white":
    #     user_content = "Game start. You are White. Make the first move of the game.\n" + user_content
    return [
        {"role": "system", "content": prompt_cfg.system_instructions},
        {"role": "user", "content": user_content},
    ]


def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```") and raw.endswith("```"):
        inner = raw.split("\n", 1)
        if len(inner) == 2:
            return inner[1].rsplit("\n", 1)[0].strip()
    return raw


def process_llm_raw_move(
    raw: str,
    fen: str,
    apply_uci_fn: Callable[[str], tuple[bool, str | None]],
    log: logging.Logger,
    meta_extra: dict | None = None,
    expected_notation: Notation = "san",
):
    """Normalize, validate, and apply an LLM move reply against the current board.

    Returns (ok, uci, san, parse_ms, meta, salvage_used) -- salvage_used always False.
    """
    t0 = time.time()
    cleaned = _strip_code_fence(raw)
    parse_ms = int((time.time() - t0) * 1000)

    validator_info = parse_expected_move(cleaned, fen, expected_notation)
    ok = False
    san = None
    uci = ""
    if validator_info.get("ok"):
        uci = validator_info["uci"]
        ok, san = apply_uci_fn(uci)
    else:
        log.debug("Move not valid: %s", validator_info.get("reason"))

    meta = {
        "raw": raw,
        "validator": validator_info,
        "expected_notation": expected_notation,
    }
    if meta_extra:
        meta.update(meta_extra)
    return ok, uci, san, parse_ms, meta, False
