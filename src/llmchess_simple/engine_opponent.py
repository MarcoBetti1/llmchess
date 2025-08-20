from __future__ import annotations
import chess, chess.engine
from .config import SETTINGS

class EngineOpponent:
    def __init__(self, depth: int = 6, movetime_ms: int | None = None):
        self.engine = chess.engine.SimpleEngine.popen_uci(SETTINGS.stockfish_path)
        self.depth = depth
        self.movetime_ms = movetime_ms

    def choose(self, board: chess.Board) -> chess.Move:
        if self.movetime_ms:
            res = self.engine.play(board, chess.engine.Limit(time=self.movetime_ms / 1000))
        else:
            res = self.engine.play(board, chess.engine.Limit(depth=self.depth))
        return res.move

    def close(self):
        self.engine.quit()
