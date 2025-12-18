from __future__ import annotations
"""Interactive human opponent that only allows legal moves."""
import chess


class UserOpponent:
    name = "Human"

    def choose(self, board: chess.Board):
        """Prompt the user for a legal move; repeat until valid."""
        while True:
            print("\nYour turn. Board FEN:", board.fen())
            print(board)
            raw = input("Enter your move in SAN or UCI (e.g., e4 or e2e4): ").strip()
            if not raw:
                continue
            try:
                mv = chess.Move.from_uci(raw) if len(raw) >= 4 else None
            except Exception:
                mv = None
            if not mv:
                try:
                    mv = board.parse_san(raw)
                except Exception:
                    mv = None
            if mv and mv in board.legal_moves:
                return mv
            print("Illegal move. Please try again with a legal move.")

    def close(self):
        return
