"""
Stockfish-backed opponent.

- Resolves engine binary path from: explicit parameter, SETTINGS.stockfish_path/env, or system PATH.
- choose(): queries the engine with either fixed depth or movetime_ms to return a chess.Move.
- close(): terminates the engine process.

"""
from __future__ import annotations
import os, shutil, chess, chess.engine
from .config import SETTINGS

class EngineOpponent:
    def __init__(self, depth: int = 6, movetime_ms: int | None = None, engine_path: str | None = None):
        """Initialize engine opponent.

        engine_path precedence:
          1. explicit parameter
          2. STOCKFISH_PATH env / settings
          3. auto-detect via shutil.which('stockfish')
        Raises RuntimeError with guidance if not found.
        """
        candidate = engine_path or SETTINGS.stockfish_path or "stockfish"
        resolved = shutil.which(candidate) or (candidate if os.path.isfile(candidate) else None)
        if not resolved:
            auto = shutil.which("stockfish")
            if auto:
                resolved = auto
            else:
                raise RuntimeError(
                    f"Stockfish engine not found (candidate='{candidate}'). Install via 'brew install stockfish' on macOS, "
                    "or set environment variable STOCKFISH_PATH to the binary path, or pass --engine-path."
                )
        self.engine_path = resolved
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
        except FileNotFoundError as e:
            raise RuntimeError(f"Failed launching engine at '{self.engine_path}': {e}")
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
