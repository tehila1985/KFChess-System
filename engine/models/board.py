from typing import Optional
from engine.models.piece import Piece
from engine.models.position import Position

EMPTY = "."


class Board:
    """
    מודל נתונים טהור של הלוח — ללא פיקסלים, ללא תזמון, ללא UI.

    הגריד מאחסן token strings ('wK', 'bP', '.').
    כל הלוגיקה של מה מותר לזוז נמצאת ב-RuleEngine, לא כאן.
    Board אחראי רק על: קריאה/כתיבה לתאים, גבולות, וחסימת נתיב.
    """

    def __init__(self, board_lines):
        # כל שורת טקסט מפוצלת לרשימת tokens
        self._grid = [line.split() for line in board_lines]
        self.rows  = len(self._grid)
        self.cols  = len(self._grid[0]) if self._grid else 0

    def in_bounds(self, pos: Position) -> bool:
        """בודק שהמשבצת בתוך גבולות הלוח."""
        return 0 <= pos.row < self.rows and 0 <= pos.col < self.cols

    def get_piece(self, pos: Position) -> Optional[Piece]:
        """מחזיר את הכלי במשבצת, או None אם ריקה."""
        token = self._grid[pos.row][pos.col]
        return None if token == EMPTY else Piece.from_token(token)

    def set_piece(self, pos: Position, piece: Optional[Piece]) -> None:
        """מציב כלי במשבצת, או מרוקן אותה אם piece=None."""
        self._grid[pos.row][pos.col] = piece.token if piece is not None else EMPTY

    def is_empty(self, pos: Position) -> bool:
        return self._grid[pos.row][pos.col] == EMPTY

    def is_path_blocked(self, start: tuple, end: tuple, is_jumper: bool = False) -> bool:
        """
        בודק אם יש כלי חוסם בנתיב הישר בין start ל-end.

        is_jumper=True (פרש) — תמיד מחזיר False כי פרש קופץ מעל הכל.
        עובר תא-תא לאורך הנתיב ובודק שכל תא ריק (לא כולל היעד עצמו).
        """
        if is_jumper:
            return False
        sr, sc = start
        tr, tc = end
        dr = 0 if sr == tr else (1 if tr > sr else -1)
        dc = 0 if sc == tc else (1 if tc > sc else -1)
        r, c = sr + dr, sc + dc
        while (r, c) != (tr, tc):
            if not self.in_bounds(Position(r, c)) or not self.is_empty(Position(r, c)):
                return True
            r += dr
            c += dc
        return False

    def move_piece_coords(self, start: tuple, end: tuple) -> str:
        """מזיז כלי לפי קואורדינטות גולמיות; מחזיר את ה-token שנלכד."""
        sr, sc = start
        tr, tc = end
        captured          = self._grid[tr][tc]
        self._grid[tr][tc] = self._grid[sr][sc]
        self._grid[sr][sc] = EMPTY
        return captured
