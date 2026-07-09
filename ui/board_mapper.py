from typing import Optional
from engine.models.position import Position


class BoardMapper:
    """
    Converts pixel (x, y) coordinates into a board Position (row, col).

    cell_size: width/height of one grid cell in pixels.
    Returns None when the pixel falls outside the valid grid area
    (negative coordinates are always invalid).
    """

    def __init__(self, cell_size: int, rows: int, cols: int):
        self._cell_size = cell_size
        self._rows      = rows
        self._cols      = cols

    def to_position(self, x: int, y: int) -> Optional[Position]:
        if x < 0 or y < 0:
            return None
        col = x // self._cell_size
        row = y // self._cell_size
        if row >= self._rows or col >= self._cols:
            return None
        return Position(row, col)
