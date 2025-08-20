from __future__ import annotations
import re
import chess

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

def normalize_move(raw_text: str, fen: str) -> dict:
    """Return {'ok': bool, 'uci': str, 'san': str} or {'ok': False, 'reason': str}."""
    board = chess.Board(fen=fen)

    cand = _extract_candidate(raw_text) or ""
    cand = CASTLE_ZERO.get(cand, cand)

    # If it looks like UCI, try that
    if UCI_RE.match(cand):
        try:
            mv = chess.Move.from_uci(cand.lower())
            if mv in board.legal_moves:
                return {"ok": True, "uci": mv.uci(), "san": board.san(mv)}
            return {"ok": False, "reason": f"Illegal UCI move for this position: {cand}"}
        except Exception as e:
            return {"ok": False, "reason": f"Invalid UCI: {cand} ({e})"}

    # Try SAN
    try:
        mv = board.parse_san(cand)
        return {"ok": True, "uci": mv.uci(), "san": board.san(mv)}
    except Exception:
        pass

    # Last resort: look for any legal SAN that appears in text
    legal = list(board.legal_moves)
    legal_sans = {board.san(m): m for m in legal}
    for san, mv in legal_sans.items():
        if san in raw_text:
            return {"ok": True, "uci": mv.uci(), "san": san}

    return {"ok": False, "reason": "Could not find a legal move in the reply."}
