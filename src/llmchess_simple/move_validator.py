"""
Move parsing/validation helpers for free-form LLM replies.

- Extracts candidate UCI or SAN (incl. 0-0/O-O castling) from text.
- Validates against a given FEN using python-chess; caches legal UCI moves per FEN.
- Exposes normalize_move(...) for robust salvage, plus is_legal_uci(...) and legal_moves(...).

Used by GameRunner to validate/salvage LLM outputs; see README for overall flow.
"""
from __future__ import annotations
import re
import chess
from functools import lru_cache

UCI_RE = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$", re.I)
CASTLE_ZERO = {"0-0": "O-O", "0-0-0": "O-O-O", "o-o": "O-O", "o-o-o": "O-O-O"}

def _extract_candidate(text: str) -> str | None:
    # Try UCI first
    m = re.search(r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b", text.lower())
    if m:
        return m.group(1)
    # Try SAN patterns (incl castling)
    tokens = re.findall(r"[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?|O-O-O|O-O|0-0-0|0-0", text)
    return tokens[0] if tokens else None

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

def normalize_move(raw_text: str, fen: str) -> dict:
    """Return {'ok': bool, 'uci': str, 'san': str} or {'ok': False, 'reason': str}."""
    board = chess.Board(fen=fen)

    cand = _extract_candidate(raw_text) or ""
    cand = CASTLE_ZERO.get(cand, cand)

    # If it looks like UCI, try that
    if UCI_RE.match(cand):
        if is_legal_uci(cand.lower(), fen):
            mv = chess.Move.from_uci(cand.lower())
            return {"ok": True, "uci": mv.uci(), "san": board.san(mv)}
        return {"ok": False, "reason": f"Illegal UCI move for this position: {cand}"}

    # Try SAN
    try:
        mv = board.parse_san(cand)
        return {"ok": True, "uci": mv.uci(), "san": board.san(mv)}
    except Exception:
        pass

    # Last resort: look for any legal SAN that appears in text
    legal = list(board.legal_moves)
    legal_sans = {board.san(m): m for m in legal}
    lower = raw_text.lower()
    for san, mv in legal_sans.items():
        if san.lower() in lower:
            return {"ok": True, "uci": mv.uci(), "san": san}

    return {"ok": False, "reason": "Could not find a legal move in the reply."}

__all__ = [
    "normalize_move",
    "is_legal_uci",
    "legal_moves",
]
