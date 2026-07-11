from typing import Optional
from engine.game_engine import GameEngine, RequestMoveResult
from engine.models.position import Position
from ui.board_mapper import BoardMapper


class Controller:
    """
    מתרגם קליקים של משתמש לבקשות תנועה.

    לוגיקת שני-קליקים:
    - קליק ראשון: בחירת כלי (שמירת src)
    - קליק שני: ניסיון תנועה מ-src ל-dst

    מקרים מיוחדים:
    - קליק מחוץ ללוח → מאפס בחירה
    - קליק על כלי ידידותי כשיש בחירה → מחליף בחירה לכלי החדש
    - קליק על תא ריק כ-src → שומר כ-src (GameEngine ידחה אם ריק)

    Controller לא מכיר כללי שחמט — הוא רק מנהל state של בחירה.
    """

    def __init__(self, engine: GameEngine, mapper: BoardMapper):
        self._engine = engine
        self._mapper = mapper
        self._src: Optional[Position] = None  # המשבצת שנבחרה בקליק הראשון

    @property
    def pending_src(self) -> Optional[Position]:
        """המשבצת הנבחרת כרגע (None אם אין בחירה)."""
        return self._src

    def on_click(self, x: int, y: int) -> Optional[RequestMoveResult]:
        """
        מטפל בקליק בפיקסל (x, y).

        מחזיר RequestMoveResult אם בוצעה בקשת תנועה, אחרת None.
        """
        pos = self._mapper.to_position(x, y)

        # קליק מחוץ ללוח — מאפס בחירה
        if pos is None:
            self._src = None
            return None

        # קליק ראשון — בחירת מקור
        if self._src is None:
            self._src = pos
            return None

        # קליק שני על כלי ידידותי — החלפת בחירה
        src       = self._src
        src_piece = self._engine.get_piece_at(src)
        dst_piece = self._engine.get_piece_at(pos)
        if src_piece is not None and dst_piece is not None and src_piece.color == dst_piece.color:
            self._src = pos
            return None

        # קליק שני על יעד — ניסיון תנועה
        self._src = None
        return self._engine.request_move(src, pos)
