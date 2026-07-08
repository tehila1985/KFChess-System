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


class QueenRule(MovementRule):
    def is_legal(self, start, end, board):
        return RookRule().is_legal(start, end, board) or BishopRule().is_legal(start, end, board)


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
        if not piece: return False
        
        color = piece[0] # 'w' או 'b'
        direction = -1 if color == 'w' else 1
        
        # 1. תנועה רגילה: קדימה בקו ישר למשבצת ריקה
        if sc == tc and tr == sr + direction:
            return board.is_empty(tr, tc)
            
        # 2. לכידה: אלכסון למשבצת שיש בה אויב
        if abs(sc - tc) == 1 and tr == sr + direction:
            target = board.get(tr, tc)
            return target != "." and target[0] != color
            
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
    _registry = {}

    @classmethod
    def register(cls, piece_type):
        cls._registry[piece_type.code] = piece_type

    @classmethod
    def get(cls, code):
        return cls._registry.get(code)
    

MOVE_DURATION_MS = {
    'K': 1000,
    'Q': 2000,
    'R': 2000,
    'B': 2000,
    'N': 3000,
    'P': 500,
}

PieceRegistry.register(PieceType('K', KingRule(),   MOVE_DURATION_MS['K'], float('inf')))
PieceRegistry.register(PieceType('Q', QueenRule(),  MOVE_DURATION_MS['Q'], 9))
PieceRegistry.register(PieceType('R', RookRule(),   MOVE_DURATION_MS['R'], 5))
PieceRegistry.register(PieceType('B', BishopRule(), MOVE_DURATION_MS['B'], 3))
PieceRegistry.register(PieceType('N', KnightRule(), MOVE_DURATION_MS['N'], 3))
PieceRegistry.register(PieceType('P', PawnRule(),   MOVE_DURATION_MS['P'], 1))
