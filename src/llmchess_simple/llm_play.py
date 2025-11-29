from __future__ import annotations
"""
Shared helpers for building prompts and processing LLM moves.

These utilities keep GameRunner and LLM-based opponents symmetric and
provider-agnostic.
"""
import logging
import re
import time
from typing import Callable

import chess

from .move_validator import normalize_move
from .prompting import PromptConfig, build_plaintext_messages, build_fen_messages, build_fen_plaintext_messages


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
    """Construct prompt messages for the given board/side using the configured mode."""
    history = annotated_history_from_board(board)
    mode = (prompt_cfg.mode or "plaintext").lower()
    if mode == "fen":
        fen = board.fen()
        pgn_tail = pgn_tail_from_board(board, pgn_tail_plies)
        return build_fen_messages(fen=fen, pgn_tail=pgn_tail, side=side, is_starting=is_starting, cfg=prompt_cfg)
    if mode in ("fen+plaintext", "fen_plaintext", "fen-and-plaintext"):
        fen = board.fen()
        return build_fen_plaintext_messages(fen=fen, side=side, history_text=history, is_starting=is_starting, cfg=prompt_cfg)
    return build_plaintext_messages(side=side, history_text=history, is_starting=is_starting, cfg=prompt_cfg)


def _extract_candidate(raw: str) -> str:
    # Try to pick a sensible move-like token from the raw reply
    m = re.search(r"\b([a-h][1-8][a-h][1-8][qrbnQ R B N]?)\b", raw, re.IGNORECASE)
    if m:
        return m.group(1).strip().lower()
    tokens = re.findall(r"[A-Za-z0-9=+-]+", raw)
    return tokens[0].lower() if tokens else ""


def process_llm_raw_move(raw: str, fen: str, apply_uci_fn: Callable[[str], tuple[bool, str | None]], salvage_with_validator: bool, verbose_llm: bool, log: logging.Logger, meta_extra: dict | None = None):
    """Normalize, validate, and apply an LLM move reply against the current board.

    Returns (ok, uci, san, parse_ms, meta, salvage_used)
    """
    t0 = time.time()
    candidate = _extract_candidate(raw)
    parse_ms = int((time.time() - t0) * 1000)

    salvage_used = False
    validator_info = None

    ok = False
    san = None
    uci = ""
    if candidate:
        validator_info = normalize_move(candidate, fen)
        if validator_info.get("ok"):
            uci = validator_info["uci"]
            ok, san = apply_uci_fn(uci)
        else:
            log.debug("Candidate not legal: %s", validator_info.get("reason"))
    else:
        log.warning("No candidate extracted from LLM reply")

    if (not ok) and salvage_with_validator:
        # Try salvage on full raw reply
        v2 = normalize_move(raw, fen)
        if v2.get("ok"):
            salvage_used = True
            uci = v2["uci"]
            ok, san = apply_uci_fn(uci)
            if ok:
                log.info("Salvaged move from raw reply: %s", uci)
        else:
            validator_info = v2

    if verbose_llm:
        log.info("LLM raw='%s' candidate='%s' ok=%s", raw, uci, ok)

    meta = {
        "raw": raw,
        "salvage_used": salvage_used,
        "validator": validator_info,
    }
    if meta_extra:
        meta.update(meta_extra)
    return ok, uci, san, parse_ms, meta, salvage_used
