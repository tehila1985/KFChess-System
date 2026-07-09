from typing import Optional
from engine.game_engine import GameEngine, RequestMoveResult
from engine.models.position import Position
from ui.board_mapper import BoardMapper


class Controller:
    """
    Translates raw pixel input into game commands.

    State machine:
      - First click  → selects the source square (stored in _src).
      - Second click → calls engine.request_move(src, dst) and clears selection.

    Clicking an out-of-bounds pixel cancels any pending selection.
    Contains zero chess logic.
    """

    def __init__(self, engine: GameEngine, mapper: BoardMapper):
        self._engine = engine
        self._mapper = mapper
        self._src: Optional[Position] = None

    @property
    def pending_src(self) -> Optional[Position]:
        """The currently selected source square, or None."""
        return self._src

    def on_click(self, x: int, y: int) -> Optional[RequestMoveResult]:
        """
        Handle a pixel click.

        Returns:
          - None              when a source square is selected (first click).
          - RequestMoveResult when a move is submitted (second click).
          - None              when the click is out-of-bounds (selection cleared).
        """
        pos = self._mapper.to_position(x, y)

        if pos is None:
            self._src = None
            return None

        if self._src is None:
            self._src = pos
            return None

        src, self._src = self._src, None
        return self._engine.request_move(src, pos)
