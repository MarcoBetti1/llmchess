"""
Move parsing/validation helpers for LLM replies.

Supports explicit expected_notation modes:
- "uci": require a legal long algebraic move (e2e4, e7e8q).
- "san": require legal SAN (e4, Nf3, O-O).
- "fen": require the resulting board FEN after the move. We match the FEN
  against every legal move from the current position to find the move.
"""
from __future__ import annotations

import chess
import re
from functools import lru_cache
from typing import Literal, TypedDict

UCI_RE = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$", re.I)
CASTLE_ZERO = {"0-0": "O-O", "0-0-0": "O-O-O", "o-o": "O-O", "o-o-o": "O-O-O"}

Notation = Literal["san", "uci", "fen"]


class ParsedMove(TypedDict, total=False):
    ok: bool
    uci: str
    san: str
    reason: str
    expected: str


def _strip_code_fence(text: str) -> str:
    """Remove simple ``` fences if present."""
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        inner = text.split("\n", 1)
        if len(inner) == 2:
            return inner[1].rsplit("\n", 1)[0].strip()
    return text


def _primary_token(text: str) -> str:
    text = _strip_code_fence(text).strip()
    tokens = text.replace("\n", " ").split()
    return tokens[0] if tokens else ""


def _first_line(text: str) -> str:
    text = _strip_code_fence(text).strip()
    return text.splitlines()[0].strip() if text else ""


@lru_cache(maxsize=8192)
def _legal_moves_set(fen: str) -> set[str]:
    """Cache and return the set of legal UCI moves for a given FEN."""
    board = chess.Board(fen=fen)
    return {m.uci() for m in board.legal_moves}


def is_legal_uci(uci: str, fen: str) -> bool:
    """Fast legality check for a UCI move in a given FEN (no SAN computation)."""
    if not UCI_RE.match(uci):
        return False
    return uci.lower() in _legal_moves_set(fen)


def legal_moves(fen: str) -> list[str]:
    """Return list of legal UCI moves for the FEN (cached)."""
    return sorted(_legal_moves_set(fen))


def _boards_equivalent(a: chess.Board, b: chess.Board) -> bool:
    """Compare board state ignoring move counters but including side/castling/ep/pieces."""
    if a.turn != b.turn:
        return False
    if a.castling_rights != b.castling_rights:
        return False
    if b.ep_square is not None and a.ep_square != b.ep_square:
        return False
    if a.ep_square is not None and b.ep_square is not None and a.ep_square != b.ep_square:
        return False
    return a.piece_map() == b.piece_map()


def _match_fen_to_move(candidate_board: chess.Board, board: chess.Board) -> ParsedMove:
    """Find the legal move whose resulting board matches candidate_board (tolerant of clocks)."""
    for mv in board.legal_moves:
        tmp = board.copy()
        tmp.push(mv)
        if _boards_equivalent(tmp, candidate_board):
            return {"ok": True, "uci": mv.uci(), "san": board.san(mv)}
    return {"ok": False, "reason": "fen_not_match_legal_move"}


def parse_expected_move(raw_text: str, fen: str, expected: Notation = "san") -> ParsedMove:
    """
    Parse a move using the requested notation. No cross-notation salvage.
    Returns ParsedMove with ok/uci/san or a reason on failure.
    """
    expected = (expected or "san").lower()
    board = chess.Board(fen=fen)
    token = _first_line(raw_text) if expected == "fen" else _primary_token(raw_text)

    if not token:
        return {"ok": False, "reason": "empty_reply", "expected": expected}

    if expected == "uci":
        token = token.lower()
        if token in CASTLE_ZERO:
            rank = "1" if board.turn == chess.WHITE else "8"
            token = f"e{rank}g{rank}" if token in {"0-0", "o-o"} else f"e{rank}c{rank}"
        if not UCI_RE.fullmatch(token):
            return {"ok": False, "reason": "bad_uci_format", "expected": expected}
        try:
            mv = chess.Move.from_uci(token)
        except Exception:
            return {"ok": False, "reason": "bad_uci_parse", "expected": expected}
        if mv not in board.legal_moves:
            return {"ok": False, "reason": "illegal_move", "expected": expected}
        return {"ok": True, "uci": mv.uci(), "san": board.san(mv), "expected": expected}

    if expected == "fen":
        try:
            target_board = chess.Board(fen=token)
        except Exception:
            return {"ok": False, "reason": "invalid_fen", "expected": expected}
        match = _match_fen_to_move(target_board, board)
        match["expected"] = expected
        if not match.get("ok"):
            match["provided_fen"] = token
        return match

    # Default to SAN
    token = CASTLE_ZERO.get(token, token)
    try:
        mv = board.parse_san(token)
    except Exception:
        return {"ok": False, "reason": "bad_san", "expected": expected}
    if mv not in board.legal_moves:
        return {"ok": False, "reason": "illegal_move", "expected": expected}
    return {"ok": True, "uci": mv.uci(), "san": board.san(mv), "expected": expected}


def normalize_move(raw_text: str, fen: str, expected: Notation = "san") -> ParsedMove:
    """Backwards-compatible wrapper using explicit notation."""
    return parse_expected_move(raw_text, fen, expected)


__all__ = [
    "parse_expected_move",
    "normalize_move",
    "is_legal_uci",
    "legal_moves",
    "Notation",
]
