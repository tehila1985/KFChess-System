from __future__ import annotations
from enum import Enum, auto
from abc import ABC, abstractmethod

from engine.models.board import Board
from engine.models.move import Move
from engine.models.position import Position
from engine.config import WHITE, WHITE_DIRECTION, BLACK_DIRECTION


class MoveStatus(Enum):
    """תוצאת אימות תנועה — מוחזרת מ-RuleEngine.validate_move."""
    OK                   = auto()
    OUTSIDE_BOARD        = auto()
    EMPTY_SOURCE         = auto()   # אין כלי במשבצת המקור
    FRIENDLY_DESTINATION = auto()   # היעד תפוס על ידי כלי ידידותי
    ILLEGAL_PIECE_MOVE   = auto()   # התנועה לא חוקית לסוג הכלי


# ── Strategy Pattern: MovementRule ────────────────────────────────────
#
# כל סוג כלי מממש MovementRule בנפרד.
# יתרון: הוספת כלי חדש = הוספת class אחד + רישום ב-_RULES.
# RuleEngine לא יודע כלום על סוגי כלים ספציפיים.

class MovementRule(ABC):
    @abstractmethod
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        """בדיקה גיאומטרית בלבד — חסימת נתיב נבדקת ב-RuleEngine."""

    def is_jumper(self) -> bool:
        """האם הכלי קופץ מעל כלים אחרים (כמו פרש)."""
        return False


class KingRule(MovementRule):
    # מלך זז בדיוק משבצת אחת בכל כיוון (כולל אלכסון)
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return max(abs(src.row - dst.row), abs(src.col - dst.col)) == 1


class RookRule(MovementRule):
    # צריח זז בקו ישר (שורה או עמודה)
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return src.row == dst.row or src.col == dst.col


class BishopRule(MovementRule):
    # רץ זז באלכסון — הפרש בשורות שווה לפרש בעמודות
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return abs(src.row - dst.row) == abs(src.col - dst.col)


class QueenRule(MovementRule):
    # מלכה = צריח + רץ
    _rook   = RookRule()
    _bishop = BishopRule()

    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return self._rook.is_legal(src, dst, board) or self._bishop.is_legal(src, dst, board)


class KnightRule(MovementRule):
    # פרש זז בצורת L: 2+1 או 1+2 משבצות
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        dr, dc = abs(src.row - dst.row), abs(src.col - dst.col)
        return (dr == 2 and dc == 1) or (dr == 1 and dc == 2)

    def is_jumper(self) -> bool:
        # פרש קופץ מעל כלים — is_path_blocked לא רלוונטי עבורו
        return True


class PawnRule(MovementRule):
    """
    חייל — הכלי המורכב ביותר:
    - זז קדימה (לפי צבע) לתא ריק
    - יכול לזוז 2 תאים מהשורה ההתחלתית (אם שניהם ריקים)
    - לוכד רק באלכסון (לא קדימה)
    """
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        piece = board.get_piece(src)
        if piece is None:
            return False

        direction = WHITE_DIRECTION if piece.color == WHITE else BLACK_DIRECTION
        start_row = board.rows - 1 if piece.color == WHITE else 0

        # צעד אחד קדימה לתא ריק
        if src.col == dst.col and dst.row == src.row + direction:
            return board.is_empty(dst)

        # שני צעדים קדימה מהשורה ההתחלתית — שני התאים חייבים להיות ריקים
        mid = Position(src.row + direction, src.col)
        if src.col == dst.col and src.row == start_row and dst.row == src.row + 2 * direction:
            return board.is_empty(mid) and board.is_empty(dst)

        # לכידה אלכסונית — חייב להיות כלי אויב ביעד
        if abs(src.col - dst.col) == 1 and dst.row == src.row + direction:
            target = board.get_piece(dst)
            return target is not None and target.color != piece.color

        return False


# ── Rule registry ──────────────────────────────────────────────────────
# מילון סטטי: type_code → MovementRule instance.
# כל הכלים הם singletons — אין state, אפשר לשתף.
_RULES: dict[str, MovementRule] = {
    'K': KingRule(),
    'Q': QueenRule(),
    'R': RookRule(),
    'B': BishopRule(),
    'N': KnightRule(),
    'P': PawnRule(),
}


def get_rule(type_code: str) -> MovementRule | None:
    return _RULES.get(type_code)


# ── RuleEngine ─────────────────────────────────────────────────────────

class RuleEngine:
    """
    Stateless validator — לא שומר state, לא משנה את הלוח.

    אחריות יחידה: לקבל (board, move) ולהחזיר MoveStatus.
    סדר הבדיקות:
      1. גבולות לוח
      2. קיום כלי במקור
      3. יעד לא תפוס על ידי ידידותי
      4. חוקיות גיאומטרית לפי סוג הכלי
      5. חסימת נתיב (לא רלוונטי לפרש)
    """

    def validate_move(self, board: Board, move: Move) -> MoveStatus:
        src, dst = move.src, move.dst

        if not board.in_bounds(src) or not board.in_bounds(dst):
            return MoveStatus.OUTSIDE_BOARD

        piece = board.get_piece(src)
        if piece is None:
            return MoveStatus.EMPTY_SOURCE

        target = board.get_piece(dst)
        if target is not None and target.color == piece.color:
            return MoveStatus.FRIENDLY_DESTINATION

        rule = get_rule(piece.type_code)
        if rule is None or not rule.is_legal(src, dst, board):
            return MoveStatus.ILLEGAL_PIECE_MOVE

        # חסימת נתיב — פרש פטור (is_jumper=True)
        if board.is_path_blocked((src.row, src.col), (dst.row, dst.col), rule.is_jumper()):
            return MoveStatus.ILLEGAL_PIECE_MOVE

        return MoveStatus.OK
