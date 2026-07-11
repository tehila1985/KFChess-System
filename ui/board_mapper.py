from typing import Optional
from engine.models.position import Position


class BoardMapper:
    """
    ממיר קואורדינטות פיקסל (x, y) למשבצת בלוח (row, col).

    הסיבה לקובץ נפרד: שכבת ה-UI היחידה שמכירה פיקסלים.
    GameEngine ו-RuleEngine לא יודעים כלום על גדלי תאים.

    חישוב: col = x // cell_size, row = y // cell_size
    קואורדינטות שליליות או מחוץ לגריד → None.
    """

    def __init__(self, cell_size: int, rows: int, cols: int):
        self._cell_size = cell_size
        self._rows      = rows
        self._cols      = cols

    def to_position(self, x: int, y: int) -> Optional[Position]:
        """מחזיר Position, או None אם הקליק מחוץ ללוח."""
        if x < 0 or y < 0:
            return None
        col = x // self._cell_size
        row = y // self._cell_size
        if row >= self._rows or col >= self._cols:
            return None
        return Position(row, col)
