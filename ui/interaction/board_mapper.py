from typing import Optional

from engine.models.position import Position


class BoardMapper:
    """
    Converts pixel coordinates (x, y) to a board square (row, col).

    This is the only UI module that knows about pixel-to-grid conversion.
    """

    def __init__(self, cell_size: int, rows: int, cols: int):
        self._cell_size = cell_size
        self._rows = rows
        self._cols = cols

    def to_position(self, x: int, y: int) -> Optional[Position]:
        """Returns a Position, or None if the click is outside the board."""
        if x < 0 or y < 0:
            return None
        col = x // self._cell_size
        row = y // self._cell_size
        if row >= self._rows or col >= self._cols:
            return None
        return Position(row, col)
