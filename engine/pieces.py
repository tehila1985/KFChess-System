from engine.config import (
    MOVE_DURATION_MS, PIECE_SCORE, JUMP_DURATION_MS,
    WHITE, BLACK, PAWN, KING, WHITE_DIRECTION, BLACK_DIRECTION,
    EMPTY_CELL
)


class MovementRule:
    def is_legal(self, start, end, board):
        raise NotImplementedError

    def is_jumper(self):
        return False


class KingRule(MovementRule):
    def is_legal(self, start, end, board):
        return max(abs(start[0] - end[0]), abs(start[1] - end[1])) == 1


class RookRule(MovementRule):
    def is_legal(self, start, end, board):
        return start[0] == end[0] or start[1] == end[1]


class BishopRule(MovementRule):
    def is_legal(self, start, end, board):
        return abs(start[0] - end[0]) == abs(start[1] - end[1])


# ⭐ Instances created once, reused everywhere (DRY fix)
_ROOK_RULE = RookRule()
_BISHOP_RULE = BishopRule()


class QueenRule(MovementRule):
    """
    מלכה משלבת תנועות צריח ורץ.
    משתמשת בsingletons של RookRule וBishopRule כדי למנוע יצירת instances חדשות.
    """
    def is_legal(self, start, end, board):
        return _ROOK_RULE.is_legal(start, end, board) or _BISHOP_RULE.is_legal(start, end, board)


class KnightRule(MovementRule):
    def is_legal(self, start, end, board):
        dx, dy = abs(start[0] - end[0]), abs(start[1] - end[1])
        return (dx == 2 and dy == 1) or (dx == 1 and dy == 2)

    def is_jumper(self):
        return True




class PawnRule(MovementRule):
    def is_legal(self, start, end, board):
        sr, sc = start
        tr, tc = end
        piece = board.get(sr, sc)
        if not piece:
            return False

        color = piece[0]
        direction = WHITE_DIRECTION if color == WHITE else BLACK_DIRECTION
        start_row = board.rows - 1 if color == WHITE else 0

        # תנועה רגילה: קדימה משבצת אחת למשבצת ריקה
        if sc == tc and tr == sr + direction:
            return board.is_empty(tr, tc)

        # תנועה כפולה: 2 משבצות קדימה משורת ההתחלה, הנתיב חייב להיות פנוי
        if sc == tc and sr == start_row and tr == sr + 2 * direction:
            return board.is_empty(sr + direction, sc) and board.is_empty(tr, tc)

        # לכידה: אלכסון למשבצת שיש בה אויב
        if abs(sc - tc) == 1 and tr == sr + direction:
            target = board.get(tr, tc)
            return target != EMPTY_CELL and target[0] != color

        return False
    
class PieceType:
    def __init__(self, code, rule, speed_ms, score):
        self.code = code
        self.rule = rule
        self.speed_ms = speed_ms
        self.score = score

    def is_legal_move(self, start, end, board):
        return self.rule.is_legal(start, end, board)

    def is_jumper(self):
        return self.rule.is_jumper()


class PieceRegistry:
    """
    מרשם מרכזי של כל הכלים וקונפיגורציה.
    עקרון Registry Pattern - כל הקונפיגורציה במקום אחד.
    """
    _registry = {}
    MOVE_DURATION_MS = MOVE_DURATION_MS
    PIECE_SCORE = PIECE_SCORE
    JUMP_DURATION_MS = JUMP_DURATION_MS

    @classmethod
    def register(cls, piece_type):
        cls._registry[piece_type.code] = piece_type

    @classmethod
    def get(cls, code):
        return cls._registry.get(code)

PieceRegistry.register(PieceType('K', KingRule(),   MOVE_DURATION_MS['K'], PIECE_SCORE['K']))
PieceRegistry.register(PieceType('Q', QueenRule(),  MOVE_DURATION_MS['Q'], PIECE_SCORE['Q']))
PieceRegistry.register(PieceType('R', RookRule(),   MOVE_DURATION_MS['R'], PIECE_SCORE['R']))
PieceRegistry.register(PieceType('B', BishopRule(), MOVE_DURATION_MS['B'], PIECE_SCORE['B']))
PieceRegistry.register(PieceType('N', KnightRule(), MOVE_DURATION_MS['N'], PIECE_SCORE['N']))
PieceRegistry.register(PieceType('P', PawnRule(),   MOVE_DURATION_MS['P'], PIECE_SCORE['P']))
