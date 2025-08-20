from __future__ import annotations
import random
import chess

class RandomOpponent:
    """Simple opponent that picks a uniformly random legal move.
    Useful for fast, low-difficulty bulk testing of LLM prompting logic.
    """
    name: str = "Random"

    def choose(self, board: chess.Board) -> chess.Move:
        legal = list(board.legal_moves)
        return random.choice(legal) if legal else chess.Move.null()

    def close(self):
        # No engine resources to release
        pass
