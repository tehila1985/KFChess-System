from __future__ import annotations
from enum import Enum, auto
from abc import ABC, abstractmethod

from engine.models.board import Board
from engine.models.move import Move
from engine.models.position import Position
from engine.config import WHITE, WHITE_DIRECTION, BLACK_DIRECTION


class MoveStatus(Enum):
    """Result of move validation — returned from RuleEngine.validate_move."""
    OK                   = auto()
    OUTSIDE_BOARD        = auto()
    EMPTY_SOURCE         = auto()   # no piece at the source square
    FRIENDLY_DESTINATION = auto()   # destination occupied by a friendly piece
    ILLEGAL_PIECE_MOVE   = auto()   # move is not legal for this piece type


# ── Strategy Pattern: MovementRule ────────────────────────────────────
#
# Each piece type implements MovementRule separately.
# Advantage: adding a new piece = adding one class + registering it in _RULES.
# RuleEngine knows nothing about specific piece types.

class MovementRule(ABC):
    @abstractmethod
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        """Geometric check only — path blocking is checked in RuleEngine."""

    def is_jumper(self) -> bool:
        """Whether the piece jumps over other pieces (like a knight)."""
        return False


class KingRule(MovementRule):
    # king moves exactly one square in any direction (including diagonals)
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return max(abs(src.row - dst.row), abs(src.col - dst.col)) == 1


class RookRule(MovementRule):
    # rook moves in a straight line (row or column)
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return src.row == dst.row or src.col == dst.col


class BishopRule(MovementRule):
    # bishop moves diagonally — row difference equals column difference
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return abs(src.row - dst.row) == abs(src.col - dst.col)


class QueenRule(MovementRule):
    # queen = rook + bishop
    _rook   = RookRule()
    _bishop = BishopRule()

    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return self._rook.is_legal(src, dst, board) or self._bishop.is_legal(src, dst, board)


class KnightRule(MovementRule):
    # knight moves in an L-shape: 2+1 or 1+2 squares
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        dr, dc = abs(src.row - dst.row), abs(src.col - dst.col)
        return (dr == 2 and dc == 1) or (dr == 1 and dc == 2)

    def is_jumper(self) -> bool:
        # knight jumps over pieces — is_path_blocked is not relevant for it
        return True


class PawnRule(MovementRule):
    """
    Pawn — the most complex piece:
    - moves forward (by color) to an empty square
    - can move 2 squares from the starting row (if both are empty)
    - captures only diagonally (not straight ahead)
    """
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        piece = board.get_piece(src)
        if piece is None:
            return False

        direction = WHITE_DIRECTION if piece.color == WHITE else BLACK_DIRECTION
        start_row = board.rows - 1 if piece.color == WHITE else 0

        # one step forward to an empty square
        if src.col == dst.col and dst.row == src.row + direction:
            return board.is_empty(dst)

        # two steps forward from the starting row — both squares must be empty
        mid = Position(src.row + direction, src.col)
        if src.col == dst.col and src.row == start_row and dst.row == src.row + 2 * direction:
            return board.is_empty(mid) and board.is_empty(dst)

        # diagonal capture — must be an enemy piece at the destination
        if abs(src.col - dst.col) == 1 and dst.row == src.row + direction:
            target = board.get_piece(dst)
            return target is not None and target.color != piece.color

        return False


# ── Rule registry ──────────────────────────────────────────────────────
# Static dictionary: type_code → MovementRule instance.
# All rules are singletons — no state, safe to share.
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
    Stateless validator — holds no state, does not modify the board.

    Single responsibility: receive (board, move) and return MoveStatus.
    Validation order:
      1. Board bounds
      2. Piece exists at source
      3. Destination not occupied by a friendly piece
      4. Geometric legality by piece type
      5. Path blocking (not relevant for knights)
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

        # path blocking — knights are exempt (is_jumper=True)
        if board.is_path_blocked((src.row, src.col), (dst.row, dst.col), rule.is_jumper()):
            return MoveStatus.ILLEGAL_PIECE_MOVE

        return MoveStatus.OK
