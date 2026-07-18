import pytest
from engine.models.board import Board
from engine.models.piece import Piece
from engine.models.position import Position
from engine.arbiter.real_time_arbiter import ActiveMotion, CompletedMotion, RealTimeArbiter


# ── helpers ────────────────────────────────────────────────────────────

def pos(r, c):
    return Position(r, c)

WR = Piece("w", "R")   # white rook
BR = Piece("b", "R")   # black rook
WK = Piece("w", "K")   # white king
BK = Piece("b", "K")   # black king
WP = Piece("w", "P")   # white pawn


# ── ActiveMotion dataclass ─────────────────────────────────────────────

class TestActiveMotion:
    def test_end_time(self):
        m = ActiveMotion(WR, pos(0, 0), pos(0, 3), start_time=100, duration=500)
        assert m.end_time == 600

    def test_frozen(self):
        m = ActiveMotion(WR, pos(0, 0), pos(0, 3), start_time=0, duration=1000)
        with pytest.raises(Exception):
            m.duration = 999  # type: ignore


# ── start_motion ───────────────────────────────────────────────────────

class TestStartMotion:
    def test_clears_source_immediately(self):
        b = Board(["wR . ."])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        assert b.is_empty(pos(0, 0))

    def test_destination_not_yet_set(self):
        b = Board(["wR . ."])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        assert b.is_empty(pos(0, 2))

    def test_motion_registered(self):
        b = Board(["wR . ."])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        assert len(arb.active_motions) == 1

    def test_multiple_motions_registered(self):
        b = Board(["wR . bR"])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 1), duration=500)
        arb.start_motion(BR, pos(0, 2), pos(0, 1), duration=500)
        assert len(arb.active_motions) == 2


# ── advance_time — basic completion ────────────────────────────────────

class TestAdvanceTime:
    def test_no_completion_before_duration(self):
        b = Board(["wR . ."])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        result = arb.advance_time(500)
        assert result == []
        assert len(arb.active_motions) == 1

    def test_completes_exactly_at_duration(self):
        b = Board(["wR . ."])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        result = arb.advance_time(1000)
        assert len(result) == 1
        assert result[0].piece == WR
        assert result[0].dst == pos(0, 2)

    def test_piece_placed_on_board_after_completion(self):
        b = Board(["wR . ."])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        arb.advance_time(1000)
        assert b.get_piece(pos(0, 2)) == WR

    def test_motion_removed_from_active_after_completion(self):
        b = Board(["wR . ."])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        arb.advance_time(1000)
        assert arb.active_motions == []

    def test_clock_accumulates_across_calls(self):
        b = Board(["wR . ."])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        arb.advance_time(400)
        arb.advance_time(400)
        assert arb.active_motions != []   # not yet
        arb.advance_time(200)
        assert arb.active_motions == []   # now done

    def test_current_time_updated(self):
        b = Board(["wR . ."])
        arb = RealTimeArbiter(b)
        arb.advance_time(300)
        arb.advance_time(200)
        assert arb.current_time == 500


# ── capture on arrival ─────────────────────────────────────────────────

class TestCaptureOnArrival:
    def test_capture_returns_captured_piece(self):
        b = Board(["wR . bR"])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        result = arb.advance_time(1000)
        assert result[0].captured == BR

    def test_captured_piece_replaced_on_board(self):
        b = Board(["wR . bR"])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        arb.advance_time(1000)
        assert b.get_piece(pos(0, 2)) == WR

    def test_no_capture_returns_none(self):
        b = Board(["wR . ."])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        result = arb.advance_time(1000)
        assert result[0].captured is None

    def test_king_capture_detected(self):
        b = Board(["wR . bK"])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        result = arb.advance_time(1000)
        assert result[0].captured == BK


# ── head-to-head collision ─────────────────────────────────────────────

class TestHeadToHead:
    def test_earlier_starter_wins(self):
        # WR starts at t=0, BR starts at t=100 — WR wins
        b = Board(["wR . bR"])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)   # t=0
        arb.advance_time(100)
        arb.start_motion(BR, pos(0, 2), pos(0, 0), duration=900)    # t=100, ends t=1000
        result = arb.advance_time(900)   # clock → 1000
        assert len(result) == 1
        assert result[0].piece == WR

    def test_loser_disappears_from_board(self):
        b = Board(["wR . bR"])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        arb.advance_time(100)
        arb.start_motion(BR, pos(0, 2), pos(0, 0), duration=900)
        arb.advance_time(900)
        # BR lost — its destination (0,0) should NOT have BR
        assert b.get_piece(pos(0, 0)) is None

    def test_simultaneous_start_first_registered_wins(self):
        # Both start at t=0 with same duration — first registered wins
        b = Board(["wR . bR"])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        arb.start_motion(BR, pos(0, 2), pos(0, 0), duration=1000)
        result = arb.advance_time(1000)
        assert len(result) == 1
        assert result[0].piece == WR


# ── two independent motions complete together ──────────────────────────

class TestIndependentMotions:
    def test_two_motions_both_complete(self):
        b = Board(["wR . . bR"])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 1), duration=500)
        arb.start_motion(BR, pos(0, 3), pos(0, 2), duration=500)
        result = arb.advance_time(500)
        assert len(result) == 2

    def test_two_motions_different_durations(self):
        b = Board(["wR . . bR"])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 1), duration=500)
        arb.start_motion(BR, pos(0, 3), pos(0, 2), duration=1000)
        r1 = arb.advance_time(500)
        assert len(r1) == 1 and r1[0].piece == WR
        r2 = arb.advance_time(500)
        assert len(r2) == 1 and r2[0].piece == BR

    def test_arbiter_is_sole_board_modifier(self):
        # Board state before any advance should only reflect start_motion clears
        b = Board(["wR . bR"])
        arb = RealTimeArbiter(b)
        arb.start_motion(WR, pos(0, 0), pos(0, 2), duration=1000)
        # src cleared, dst still has bR
        assert b.is_empty(pos(0, 0))
        assert b.get_piece(pos(0, 2)) == BR
        # only after advance does dst change
        arb.advance_time(1000)
        assert b.get_piece(pos(0, 2)) == WR
