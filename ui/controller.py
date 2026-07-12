from typing import Optional
from engine.game_engine import GameEngine, RequestMoveResult
from engine.models.position import Position
from ui.board_mapper import BoardMapper


class Controller:
    """
    Translates user clicks into move requests.

    Two-click logic:
    - first click: select a piece (store src)
    - second click: attempt a move from src to dst

    Special cases:
    - click outside the board -> reset selection
    - click on a friendly piece when one is already selected -> switch selection to the new piece
    - click on an empty square as src -> store as src (GameEngine will reject if empty)

    Controller knows no chess rules — it only manages selection state.
    """

    def __init__(self, engine: GameEngine, mapper: BoardMapper):
        self._engine = engine
        self._mapper = mapper
        self._src: Optional[Position] = None  # the square selected on the first click

    @property
    def pending_src(self) -> Optional[Position]:
        """The currently selected square (None if nothing is selected)."""
        return self._src

    def on_click(self, x: int, y: int) -> Optional[RequestMoveResult]:
        """
        Handles a click at pixel (x, y).

        Returns RequestMoveResult if a move request was made, otherwise None.
        """
        pos = self._mapper.to_position(x, y)

        # click outside the board — reset selection
        if pos is None:
            self._src = None
            return None

        # first click — select source
        if self._src is None:
            self._src = pos
            return None

        # second click on a friendly piece — switch selection
        src       = self._src
        src_piece = self._engine.get_piece_at(src)
        dst_piece = self._engine.get_piece_at(pos)
        if src_piece is not None and dst_piece is not None and src_piece.color == dst_piece.color:
            self._src = pos
            return None

        # second click on a destination — attempt move
        self._src = None
        return self._engine.request_move(src, pos)
