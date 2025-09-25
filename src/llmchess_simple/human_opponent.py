import chess

class HumanOpponent:
    """Opponent that defers move choice to an external controller (web UI).

    The web layer will call provide_move(uci) when the human submits a move.
    Until then, choose() raises if invoked without a pending move.
    """
    name = "Human"

    def __init__(self):
        self._pending: chess.Move | None = None

    def provide_move(self, uci: str):
        mv = chess.Move.from_uci(uci)
        self._pending = mv

    def choose(self, board: chess.Board) -> chess.Move:
        if self._pending is None:
            raise RuntimeError("Human move not yet provided")
        mv = self._pending
        self._pending = None
        return mv

    def close(self):
        pass