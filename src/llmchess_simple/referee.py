"""
Referee: centralized game state and PGN/export utilities.

- Owns a python-chess Board and applies validated moves (UCI or engine Move).
- Manages PGN headers, result overrides, and optional termination comment.
- Exposes status() for current result and pgn() to serialize finished/ongoing games.

Used by GameRunner/BatchOrchestrator to track state, record outcomes, and emit PGN.

"""
from __future__ import annotations
"""Minimal referee to apply moves, track headers, and emit PGN."""
import chess, chess.pgn, datetime
from typing import Optional

class Referee:
    """Plain chess referee around python-chess Board and PGN export."""
    def __init__(self, starting_fen: str | None = None):
        self.board = chess.Board(fen=starting_fen) if starting_fen else chess.Board()
        self._headers: dict[str, str] = {}
        self._result_override: Optional[str] = None
        self._termination_comment: Optional[str] = None

    # ---------------- Header / Result Management -----------------
    def set_headers(self, event: str = "LLM Chess Benchmark", site: str = "?", date: Optional[str] = None,
                    round_: str = "?", white: str = "?", black: str = "?") -> None:
        date = date or datetime.date.today().strftime("%Y.%m.%d")
        self._headers.update({
            "Event": event,
            "Site": site,
            "Date": date,
            "Round": round_,
            "White": white,
            "Black": black,
        })

    def set_result(self, result: str, termination_reason: Optional[str] = None) -> None:
        self._result_override = result
        if termination_reason:
            self._termination_comment = f"Termination: {termination_reason}"

    def force_result(self, result: str, termination_reason: Optional[str] = None) -> None:
        # alias to set_result
        self.set_result(result, termination_reason)

    # ---------------- Move Application -----------------
    def apply_uci(self, uci: str) -> tuple[bool, str | None]:
        try:
            mv = chess.Move.from_uci(uci)
        except Exception:
            return False, None
        if mv not in self.board.legal_moves:
            return False, None
        san = self.board.san(mv)
        self.board.push(mv)
        return True, san

    def engine_apply(self, mv: chess.Move) -> str:
        san = self.board.san(mv)
        self.board.push(mv)
        return san

    # ---------------- PGN / Status -----------------
    def pgn(self) -> str:
        game = chess.pgn.Game()
        # headers
        for k, v in self._headers.items():
            game.headers[k] = v
        game.headers["Result"] = self.status()
        node = game
        for mv in list(self.board.move_stack):
            node = node.add_variation(mv)
        if self._termination_comment:
            game.comment = self._termination_comment
        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=bool(self._termination_comment))
        return game.accept(exporter)

    def status(self) -> str:
        if self._result_override:
            return self._result_override
        if self.board.is_game_over():
            return self.board.result()
        return "*"
