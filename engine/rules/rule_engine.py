from __future__ import annotations
from enum import Enum, auto
from abc import ABC, abstractmethod

from engine.models.board import Board
from engine.models.move import Move
from engine.models.position import Position
from engine.config import WHITE, WHITE_DIRECTION, BLACK_DIRECTION


class MoveStatus(Enum):
    OK                   = auto()
    OUTSIDE_BOARD        = auto()
    EMPTY_SOURCE         = auto()
    FRIENDLY_DESTINATION = auto()
    ILLEGAL_PIECE_MOVE   = auto()


# ── Movement rules (Strategy Pattern) ─────────────────────────────────

class MovementRule(ABC):
    @abstractmethod
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        """Geometric/logical validity only — no path-blocking check here."""

    def is_jumper(self) -> bool:
        return False


class KingRule(MovementRule):
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return max(abs(src.row - dst.row), abs(src.col - dst.col)) == 1


class RookRule(MovementRule):
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return src.row == dst.row or src.col == dst.col


class BishopRule(MovementRule):
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return abs(src.row - dst.row) == abs(src.col - dst.col)


class QueenRule(MovementRule):
    _rook   = RookRule()
    _bishop = BishopRule()

    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        return self._rook.is_legal(src, dst, board) or self._bishop.is_legal(src, dst, board)


class KnightRule(MovementRule):
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        dr, dc = abs(src.row - dst.row), abs(src.col - dst.col)
        return (dr == 2 and dc == 1) or (dr == 1 and dc == 2)

    def is_jumper(self) -> bool:
        return True


class PawnRule(MovementRule):
    def is_legal(self, src: Position, dst: Position, board: Board) -> bool:
        piece = board.get_piece(src)
        if piece is None:
            return False

        direction = WHITE_DIRECTION if piece.color == WHITE else BLACK_DIRECTION
        start_row = board.rows - 1  if piece.color == WHITE else 0

        # one step forward into empty square
        if src.col == dst.col and dst.row == src.row + direction:
            return board.is_empty(dst)

        # two steps forward from starting rank
        mid = Position(src.row + direction, src.col)
        if src.col == dst.col and src.row == start_row and dst.row == src.row + 2 * direction:
            return board.is_empty(mid) and board.is_empty(dst)

        # diagonal capture
        if abs(src.col - dst.col) == 1 and dst.row == src.row + direction:
            target = board.get_piece(dst)
            return target is not None and target.color != piece.color

        return False


# ── Rule registry ──────────────────────────────────────────────────────

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
    Stateless validator. Never modifies the board.
    Path-blocking is delegated to Board.is_path_blocked.
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

        if board.is_path_blocked((src.row, src.col), (dst.row, dst.col), rule.is_jumper()):
            return MoveStatus.ILLEGAL_PIECE_MOVE

        return MoveStatus.OK
