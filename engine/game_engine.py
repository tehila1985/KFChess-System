from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from engine.models.board import Board
from engine.models.move import Move
from engine.models.piece import Piece
from engine.models.position import Position
from engine.rules.rule_engine import MoveStatus, RuleEngine
from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.config import WHITE, BLACK, KING, QUEEN, PAWN, GameConfig, DEFAULT_CONFIG


class RequestMoveResult(Enum):
    """תוצאת בקשת תנועה — מוחזרת ל-Controller אחרי request_move."""
    ACCEPTED             = auto()  # התנועה התקבלה ונמצאת בדרך
    GAME_OVER            = auto()  # המשחק הסתיים, לא מקבלים תנועות
    PIECE_BUSY           = auto()  # הכלי כבר בתנועה
    OUTSIDE_BOARD        = auto()
    EMPTY_SOURCE         = auto()
    FRIENDLY_DESTINATION = auto()
    ILLEGAL_PIECE_MOVE   = auto()


# מיפוי מ-MoveStatus (שכבת rules) ל-RequestMoveResult (שכבת engine)
_STATUS_MAP: dict[MoveStatus, RequestMoveResult] = {
    MoveStatus.OK:                   RequestMoveResult.ACCEPTED,
    MoveStatus.OUTSIDE_BOARD:        RequestMoveResult.OUTSIDE_BOARD,
    MoveStatus.EMPTY_SOURCE:         RequestMoveResult.EMPTY_SOURCE,
    MoveStatus.FRIENDLY_DESTINATION: RequestMoveResult.FRIENDLY_DESTINATION,
    MoveStatus.ILLEGAL_PIECE_MOVE:   RequestMoveResult.ILLEGAL_PIECE_MOVE,
}


@dataclass(frozen=True)
class MotionSummary:
    """סיכום תנועה פעילה — חלק מה-GameSnapshot לצורך UI."""
    piece:      Piece
    src:        Position
    dst:        Position
    start_time: int
    end_time:   int


@dataclass(frozen=True)
class GameSnapshot:
    """
    תמונת מצב של המשחק בנקודת זמן נתונה.

    נוצר על ידי get_snapshot() ומועבר ל-TextRenderer.
    frozen — לא ניתן לשינוי, בטוח להעביר לשכבת UI.
    """
    grid:           tuple   # הגריד הנוכחי (כולל כלים בתנועה ב-src שלהם)
    scores:         dict
    game_over:      bool
    winner:         Optional[str]
    active_motions: tuple   # MotionSummary של כל התנועות הפעילות


class GameEngine:
    """
    מנוע המשחק — מתאם בין כל השכבות.

    אחריות:
    - קבלת בקשות תנועה מה-Controller ואימותן דרך RuleEngine
    - העברת תנועות מאושרות ל-RealTimeArbiter
    - קידום הזמן (tick) וטיפול בתוצאות (לכידה, קידום חייל)
    - ניהול ניקוד ומצב game_over
    - יצירת GameSnapshot לצורך הצגה

    לא מכיר UI, לא מכיר פיקסלים.
    """

    def __init__(self, board: Board, rule_engine: RuleEngine, arbiter: RealTimeArbiter,
                 config: GameConfig = DEFAULT_CONFIG):
        self._board     = board
        self._rules     = rule_engine
        self._arbiter   = arbiter
        self._config    = config  # ערכי משחק מוזרקים — לא מיובאים ישירות
        self._scores    = {WHITE: 0, BLACK: 0}
        self._game_over = False
        self._winner: Optional[str] = None

    def get_piece_at(self, pos: Position) -> Optional[Piece]:
        """
        מחזיר את הכלי במשבצת — בין אם הוא על הלוח ובין אם בתנועה.

        כלי בתנועה נמחק מהגריד ב-start_motion, אז בודקים גם ב-active_motions.
        """
        piece = self._board.get_piece(pos)
        if piece is not None:
            return piece
        for m in self._arbiter.active_motions:
            if m.src == pos:
                return m.piece
        return None

    def request_move(self, src: Position, dst: Position) -> RequestMoveResult:
        """
        מנסה להתחיל תנועה מ-src ל-dst.

        סדר הבדיקות:
        1. game_over — לא מקבלים תנועות
        2. הכלי עסוק (כבר בתנועה)
        3. אימות חוקיות דרך RuleEngine
        4. חישוב משך התנועה לפי סוג הכלי ומרחק
        5. העברה ל-Arbiter
        """
        if self._game_over:
            return RequestMoveResult.GAME_OVER

        if self._is_piece_busy(src):
            return RequestMoveResult.PIECE_BUSY

        status = self._rules.validate_move(self._board, Move(src, dst))
        if status != MoveStatus.OK:
            return _STATUS_MAP[status]

        piece    = self._board.get_piece(src)
        speed    = self._config.move_duration_ms.get(piece.type_code, 1000)
        distance = max(abs(dst.row - src.row), abs(dst.col - src.col))
        duration = speed * distance
        self._arbiter.start_motion(piece, src, dst, duration)
        return RequestMoveResult.ACCEPTED

    def request_jump(self, pos: Position) -> None:
        """
        מבצע קפיצה לכלי במשבצת pos.

        קפיצה אפשרית רק אם הכלי לא בתנועה כרגע.
        הכלי נשאר במשבצתו אבל מסומן כ-airborne — יכול ללכוד מגיעים.
        """
        if self._game_over:
            return
        if not self._board.in_bounds(pos):
            return
        if self._board.get_piece(pos) is None:
            return
        if self._is_piece_busy(pos):
            return
        self._arbiter.start_jump(pos)

    def tick(self, delta_ms: int) -> None:
        """
        מקדם את הזמן ב-delta_ms ומטפל בתנועות שהסתיימו.

        לכל תנועה שהסתיימה:
        - אם חייל הגיע לקצה — מקדמים אותו למלכה
        - אם הייתה לכידה — מפעילים _apply_capture
        """
        completed = self._arbiter.advance_time(delta_ms)
        for motion in completed:
            dst   = motion.dst
            piece = self._board.get_piece(dst)
            # קידום חייל: הגיע לשורה הראשונה (לבן) או האחרונה (שחור)
            if piece is not None and piece.type_code == PAWN:
                promotion_row = 0 if piece.color == WHITE else self._board.rows - 1
                if dst.row == promotion_row:
                    self._board.set_piece(dst, Piece(piece.color, QUEEN))
            if motion.captured is not None:
                self._apply_capture(motion.captured)

    def get_snapshot(self) -> GameSnapshot:
        """
        מחזיר תמונת מצב נוכחית של המשחק.

        כלים בתנועה מוצגים ב-src שלהם בגריד (כדי שה-UI יראה אותם).
        קפיצות (is_jump) לא מוצגות ב-src כי הכלי כבר מוצג על הלוח.
        """
        grid = [list(row) for row in self._board._grid]
        for m in self._arbiter.active_motions:
            if not m.is_jump and grid[m.src.row][m.src.col] == ".":
                grid[m.src.row][m.src.col] = m.piece.token
        frozen_grid = tuple(tuple(row) for row in grid)
        motions = tuple(
            MotionSummary(m.piece, m.src, m.dst, m.start_time, m.end_time)
            for m in self._arbiter.active_motions
        )
        return GameSnapshot(
            grid           = frozen_grid,
            scores         = dict(self._scores),
            game_over      = self._game_over,
            winner         = self._winner,
            active_motions = motions,
        )

    def _is_piece_busy(self, src: Position) -> bool:
        """כלי עסוק אם יש תנועה פעילה (כולל קפיצה) שיצאה מ-src."""
        return any(m.src == src for m in self._arbiter.active_motions)

    def _apply_capture(self, captured: Piece) -> None:
        """
        מטפל בלכידת כלי:
        - לכידת מלך → game_over, הניקוד של הצד הלוכד = אינסוף
        - לכידת כלי אחר → מוסיף ניקוד לצד הלוכד
        """
        scorer = BLACK if captured.color == WHITE else WHITE
        if captured.type_code == KING:
            self._game_over = True
            self._winner    = scorer
            self._scores[scorer] = float('inf')
        else:
            self._scores[scorer] += self._config.piece_score.get(captured.type_code, 0)
