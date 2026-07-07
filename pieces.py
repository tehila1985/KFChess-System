class Piece:
    def is_legal(self, start, end):
        raise NotImplementedError

class King(Piece):
    def is_legal(self, start, end):
        return max(abs(start[0] - end[0]), abs(start[1] - end[1])) == 1

class Rook(Piece):
    def is_legal(self, start, end):
        return start[0] == end[0] or start[1] == end[1]

class Bishop(Piece):
    def is_legal(self, start, end):
        return abs(start[0] - end[0]) == abs(start[1] - end[1])

class Queen(Piece):
    def is_legal(self, start, end):
        return Rook().is_legal(start, end) or Bishop().is_legal(start, end)

class Knight(Piece):
    def is_legal(self, start, end):
        dx, dy = abs(start[0] - end[0]), abs(start[1] - end[1])
        return (dx == 2 and dy == 1) or (dx == 1 and dy == 2)