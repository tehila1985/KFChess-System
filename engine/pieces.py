class MovementRule:
    def is_legal(self, start, end):
        raise NotImplementedError

    def is_jumper(self):
        return False


class KingRule(MovementRule):
    def is_legal(self, start, end):
        return max(abs(start[0] - end[0]), abs(start[1] - end[1])) == 1


class RookRule(MovementRule):
    def is_legal(self, start, end):
        return start[0] == end[0] or start[1] == end[1]


class BishopRule(MovementRule):
    def is_legal(self, start, end):
        return abs(start[0] - end[0]) == abs(start[1] - end[1])


class QueenRule(MovementRule):
    def is_legal(self, start, end):
        return RookRule().is_legal(start, end) or BishopRule().is_legal(start, end)


class KnightRule(MovementRule):
    def is_legal(self, start, end):
        dx, dy = abs(start[0] - end[0]), abs(start[1] - end[1])
        return (dx == 2 and dy == 1) or (dx == 1 and dy == 2)

    def is_jumper(self):
        return True


class PawnRule(MovementRule):
    def is_legal(self, start, end):
        dr = end[0] - start[0]
        dc = abs(end[1] - start[1])
        return dc == 0 and dr == -1


class PieceType:
    def __init__(self, code, rule, speed_ms, score):
        self.code = code
        self.rule = rule
        self.speed_ms = speed_ms
        self.score = score

    def is_legal_move(self, start, end):
        return self.rule.is_legal(start, end)

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


PieceRegistry.register(PieceType('K', KingRule(),   300, float('inf')))
PieceRegistry.register(PieceType('Q', QueenRule(),  200, 9))
PieceRegistry.register(PieceType('R', RookRule(),   250, 5))
PieceRegistry.register(PieceType('B', BishopRule(), 250, 3))
PieceRegistry.register(PieceType('N', KnightRule(), 300, 3))
PieceRegistry.register(PieceType('P', PawnRule(),   400, 1))
