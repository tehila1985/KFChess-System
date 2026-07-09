import pytest
from engine.models.board import Board
from engine.models.move import Move
from engine.models.position import Position
from engine.rules.rule_engine import (
    RuleEngine, MoveStatus,
    KingRule, RookRule, BishopRule, QueenRule, KnightRule, PawnRule,
)


def pos(r, c):
    return Position(r, c)


def move(sr, sc, dr, dc):
    return Move(pos(sr, sc), pos(dr, dc))


# ── KingRule ───────────────────────────────────────────────────────────

class TestKingRule:
    rule = KingRule()

    def board(self):
        return Board([". . .", ". wK .", ". . ."])

    def test_one_step_all_directions(self):
        b = self.board()
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
            assert self.rule.is_legal(pos(1,1), pos(1+dr,1+dc), b)

    def test_two_steps_invalid(self):
        assert not self.rule.is_legal(pos(1,1), pos(1,3), self.board())

    def test_not_jumper(self):
        assert not self.rule.is_jumper()


# ── RookRule ───────────────────────────────────────────────────────────

class TestRookRule:
    rule = RookRule()

    def board(self):
        return Board(["wR . . .", ". . . .", ". . . ."])

    def test_horizontal(self):
        assert self.rule.is_legal(pos(0,0), pos(0,3), self.board())

    def test_vertical(self):
        assert self.rule.is_legal(pos(0,0), pos(2,0), self.board())

    def test_diagonal_invalid(self):
        assert not self.rule.is_legal(pos(0,0), pos(2,2), self.board())

    def test_not_jumper(self):
        assert not self.rule.is_jumper()


# ── BishopRule ─────────────────────────────────────────────────────────

class TestBishopRule:
    rule = BishopRule()

    def board(self):
        return Board(["wB . .", ". . .", ". . ."])

    def test_diagonal(self):
        assert self.rule.is_legal(pos(0,0), pos(2,2), self.board())

    def test_anti_diagonal(self):
        assert self.rule.is_legal(pos(0,2), pos(2,0), self.board())

    def test_straight_invalid(self):
        assert not self.rule.is_legal(pos(0,0), pos(0,2), self.board())

    def test_not_jumper(self):
        assert not self.rule.is_jumper()


# ── QueenRule ──────────────────────────────────────────────────────────

class TestQueenRule:
    rule = QueenRule()

    def board(self):
        return Board(["wQ . .", ". . .", ". . ."])

    def test_horizontal(self):
        assert self.rule.is_legal(pos(0,0), pos(0,2), self.board())

    def test_vertical(self):
        assert self.rule.is_legal(pos(0,0), pos(2,0), self.board())

    def test_diagonal(self):
        assert self.rule.is_legal(pos(0,0), pos(2,2), self.board())

    def test_invalid_l_shape(self):
        assert not self.rule.is_legal(pos(0,0), pos(1,2), self.board())


# ── KnightRule ─────────────────────────────────────────────────────────

class TestKnightRule:
    rule = KnightRule()

    def board(self):
        return Board(["wN . . .", ". . . .", ". . . ."])

    def test_l_shapes(self):
        for dr, dc in [(2,1),(2,-1),(-2,1),(-2,-1),(1,2),(1,-2),(-1,2),(-1,-2)]:
            r, c = 2 + dr, 2 + dc
            b = Board([". . . .", ". . . .", ". . wN .", ". . . ."])
            assert self.rule.is_legal(pos(2,2), pos(r,c), b)

    def test_straight_invalid(self):
        assert not self.rule.is_legal(pos(0,0), pos(0,2), self.board())

    def test_is_jumper(self):
        assert self.rule.is_jumper()

    def test_jumps_over_pieces(self):
        b = Board(["wN wP wP .", ". . . .", ". . . ."])
        # knight at (0,0) to (2,1) — pieces in the way don't matter
        assert self.rule.is_legal(pos(0,0), pos(2,1), b)


# ── PawnRule ───────────────────────────────────────────────────────────

class TestPawnRule:
    rule = PawnRule()

    def test_white_one_step_forward(self):
        b = Board([". . .", ". wP .", ". . ."])
        assert self.rule.is_legal(pos(1,1), pos(0,1), b)

    def test_white_cannot_move_backward(self):
        b = Board([". . .", ". wP .", ". . ."])
        assert not self.rule.is_legal(pos(1,1), pos(2,1), b)

    def test_white_double_step_from_start(self):
        # 4-row board: white start_row = rows-1 = 3, pawn at (3,1), target (1,1)
        b = Board([". . .", ". . .", ". . .", ". wP ."])
        assert self.rule.is_legal(pos(3,1), pos(1,1), b)

    def test_white_double_step_blocked(self):
        b = Board([". . .", ". . .", ". wP .", ". wP .", ". . ."])
        assert not self.rule.is_legal(pos(3,1), pos(1,1), b)

    def test_black_one_step_forward(self):
        b = Board([". bP .", ". . .", ". . ."])
        assert self.rule.is_legal(pos(0,1), pos(1,1), b)

    def test_white_diagonal_capture(self):
        b = Board(["bR . .", ". wP .", ". . ."])
        assert self.rule.is_legal(pos(1,1), pos(0,0), b)

    def test_cannot_capture_friendly(self):
        b = Board(["wR . .", ". wP .", ". . ."])
        assert not self.rule.is_legal(pos(1,1), pos(0,0), b)

    def test_cannot_capture_forward(self):
        # bR directly in front of wP — pawn cannot capture straight ahead
        b = Board([". bR .", ". wP .", ". . ."])
        assert not self.rule.is_legal(pos(1,1), pos(0,1), b)


# ── RuleEngine.validate_move ───────────────────────────────────────────

class TestRuleEngine:
    engine = RuleEngine()

    def test_ok_rook_move(self):
        b = Board(["wR . . ."])
        assert self.engine.validate_move(b, move(0,0,0,3)) == MoveStatus.OK

    def test_outside_board_src(self):
        b = Board(["wR . ."])
        assert self.engine.validate_move(b, move(-1,0,0,0)) == MoveStatus.OUTSIDE_BOARD

    def test_outside_board_dst(self):
        b = Board(["wR . ."])
        assert self.engine.validate_move(b, move(0,0,0,5)) == MoveStatus.OUTSIDE_BOARD

    def test_empty_source(self):
        b = Board([". . ."])
        assert self.engine.validate_move(b, move(0,0,0,2)) == MoveStatus.EMPTY_SOURCE

    def test_friendly_destination(self):
        b = Board(["wR . wB"])
        assert self.engine.validate_move(b, move(0,0,0,2)) == MoveStatus.FRIENDLY_DESTINATION

    def test_illegal_piece_move_rook_diagonal(self):
        b = Board(["wR . .", ". . .", ". . ."])
        assert self.engine.validate_move(b, move(0,0,2,2)) == MoveStatus.ILLEGAL_PIECE_MOVE

    def test_illegal_piece_move_path_blocked(self):
        b = Board(["wR wP . ."])
        # rook tries to pass through wP
        assert self.engine.validate_move(b, move(0,0,0,3)) == MoveStatus.ILLEGAL_PIECE_MOVE

    def test_knight_jumps_over_pieces(self):
        b = Board(["wN wP wP .", ". . . .", ". . . ."])
        # knight at (0,0) to (2,1) — valid L-shape, jumps over blockers
        assert self.engine.validate_move(b, move(0,0,2,1)) == MoveStatus.OK

    def test_capture_enemy_is_ok(self):
        b = Board(["wR . bR"])
        assert self.engine.validate_move(b, move(0,0,0,2)) == MoveStatus.OK

    def test_engine_does_not_modify_board(self):
        b = Board(["wR . bR"])
        before = [row[:] for row in b._grid]
        self.engine.validate_move(b, move(0,0,0,2))
        assert b._grid == before
