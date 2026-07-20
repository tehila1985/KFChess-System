from typing import Optional
from server.models.piece import Piece
from server.models.position import Position

EMPTY = "."


class Board:
    """
    Pure data model of the board — no pixels, no timing, no UI.

    The grid stores token strings ('wK', 'bP', '.').
    All logic about what is allowed to move lives in RuleEngine, not here.
    Board is only responsible for: reading/writing cells, bounds checking, and path blocking.
    """

    def __init__(self, board_lines):
        # each text row is split into a list of tokens
        self._grid = [line.split() for line in board_lines]
        self.rows  = len(self._grid)
        self.cols  = len(self._grid[0]) if self._grid else 0

    def in_bounds(self, pos: Position) -> bool:
        """Returns True if the square is within the board boundaries."""
        return 0 <= pos.row < self.rows and 0 <= pos.col < self.cols

    def get_piece(self, pos: Position) -> Optional[Piece]:
        """Returns the piece at the square, or None if empty."""
        token = self._grid[pos.row][pos.col]
        return None if token == EMPTY else Piece.from_token(token)

    def set_piece(self, pos: Position, piece: Optional[Piece]) -> None:
        """Places a piece on the square, or clears it if piece=None."""
        self._grid[pos.row][pos.col] = piece.token if piece is not None else EMPTY

    def is_empty(self, pos: Position) -> bool:
        return self._grid[pos.row][pos.col] == EMPTY

    def is_path_blocked(self, start: tuple, end: tuple, is_jumper: bool = False) -> bool:
        """
        Checks whether a piece blocks the straight path between start and end.

        is_jumper=True (knight) — always returns False because knights jump over everything.
        Walks cell by cell along the path and checks that every cell is empty (excluding the destination).
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

