import pytest
from engine.models.board import Board
from engine.models.piece import Piece
from engine.models.position import Position
from engine.rules.rule_engine import RuleEngine
from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.game_engine import GameEngine, RequestMoveResult, GameSnapshot


# ── helpers ────────────────────────────────────────────────────────────

def pos(r, c):
    return Position(r, c)


def make_engine(board_lines: list[str]) -> GameEngine:
    board   = Board(board_lines)
    arbiter = RealTimeArbiter(board)
    return GameEngine(board, RuleEngine(), arbiter)


# ── request_move — gate checks ─────────────────────────────────────────

class TestRequestMove:
    def test_accepted_valid_move(self):
        eng = make_engine(["wR . . ."])
        assert eng.request_move(pos(0, 0), pos(0, 3)) == RequestMoveResult.ACCEPTED

    def test_empty_source(self):
        eng = make_engine([". . ."])
        assert eng.request_move(pos(0, 0), pos(0, 2)) == RequestMoveResult.EMPTY_SOURCE

    def test_outside_board(self):
        eng = make_engine(["wR . ."])
        assert eng.request_move(pos(0, 0), pos(0, 9)) == RequestMoveResult.OUTSIDE_BOARD

    def test_friendly_destination(self):
        eng = make_engine(["wR . wB"])
        assert eng.request_move(pos(0, 0), pos(0, 2)) == RequestMoveResult.FRIENDLY_DESTINATION

    def test_illegal_piece_move(self):
        eng = make_engine(["wR . .", ". . .", ". . ."])
        assert eng.request_move(pos(0, 0), pos(2, 2)) == RequestMoveResult.ILLEGAL_PIECE_MOVE

    def test_piece_busy_rejected(self):
        eng = make_engine(["wR . . ."])
        eng.request_move(pos(0, 0), pos(0, 3))          # accepted, now in motion
        assert eng.request_move(pos(0, 0), pos(0, 1)) == RequestMoveResult.PIECE_BUSY

    def test_piece_on_cooldown_rejected_until_timeout(self):
        eng = make_engine(["wR . ."])
        eng.request_move(pos(0, 0), pos(0, 1))
        eng.tick(1000)  # arrival
        assert eng.request_move(pos(0, 1), pos(0, 2)) == RequestMoveResult.PIECE_ON_COOLDOWN
        eng.tick(3000)  # cooldown elapsed
        assert eng.request_move(pos(0, 1), pos(0, 2)) == RequestMoveResult.ACCEPTED

    def test_game_over_rejects_all_moves(self):
        eng = make_engine(["wR . bK"])
        eng.request_move(pos(0, 0), pos(0, 2))
        eng.tick(2000)                                   # 2 cells * 1000ms
        assert eng.request_move(pos(0, 2), pos(0, 0)) == RequestMoveResult.GAME_OVER


# ── tick — time progression ────────────────────────────────────────────

class TestTick:
    def test_piece_not_on_dst_before_tick(self):
        eng = make_engine(["wR . . ."])
        eng.request_move(pos(0, 0), pos(0, 3))
        snap = eng.get_snapshot()
        assert snap.grid[0][3] == "."

    def test_piece_arrives_after_full_duration(self):
        eng = make_engine(["wR . . ."])
        eng.request_move(pos(0, 0), pos(0, 3))
        eng.tick(3000)                                   # 3 cells * 1000ms
        snap = eng.get_snapshot()
        assert snap.grid[0][3] == "wR"

    def test_partial_tick_does_not_complete_motion(self):
        eng = make_engine(["wR . . ."])
        eng.request_move(pos(0, 0), pos(0, 3))
        eng.tick(500)
        snap = eng.get_snapshot()
        assert snap.grid[0][3] == "."
        assert len(snap.active_motions) == 1

    def test_accumulated_ticks_complete_motion(self):
        eng = make_engine(["wR . . ."])
        eng.request_move(pos(0, 0), pos(0, 3))
        eng.tick(1500)
        eng.tick(1500)
        snap = eng.get_snapshot()
        assert snap.grid[0][3] == "wR"
        assert len(snap.active_motions) == 0


# ── capture & scoring ──────────────────────────────────────────────────

class TestCapture:
    def test_score_updated_on_capture(self):
        eng = make_engine(["wR . bR"])
        eng.request_move(pos(0, 0), pos(0, 2))
        eng.tick(2000)                                   # 2 cells * 1000ms
        snap = eng.get_snapshot()
        assert snap.scores["w"] == 5

    def test_no_score_change_on_empty_arrival(self):
        eng = make_engine(["wR . ."])
        eng.request_move(pos(0, 0), pos(0, 2))
        eng.tick(1000)
        snap = eng.get_snapshot()
        assert snap.scores["w"] == 0

    def test_king_capture_ends_game(self):
        eng = make_engine(["wR . bK"])
        eng.request_move(pos(0, 0), pos(0, 2))
        eng.tick(2000)                                   # 2 cells * 1000ms
        snap = eng.get_snapshot()
        assert snap.game_over is True

    def test_king_capture_sets_winner(self):
        eng = make_engine(["wR . bK"])
        eng.request_move(pos(0, 0), pos(0, 2))
        eng.tick(2000)
        assert eng.get_snapshot().winner == "w"

    def test_black_captures_white_king(self):
        eng = make_engine(["wK . bR"])
        eng.request_move(pos(0, 2), pos(0, 0))
        eng.tick(2000)
        snap = eng.get_snapshot()
        assert snap.game_over is True
        assert snap.winner == "b"

    def test_multiple_captures_accumulate_score(self):
        eng = make_engine(["wR . bR . bB"])
        eng.request_move(pos(0, 0), pos(0, 2))
        eng.tick(2000)                                   # 2 cells
        eng.tick(3000)                                   # cooldown
        eng.request_move(pos(0, 2), pos(0, 4))
        eng.tick(2000)                                   # 2 cells
        snap = eng.get_snapshot()
        assert snap.scores["w"] == 8


# ── get_snapshot ───────────────────────────────────────────────────────

class TestGetSnapshot:
    def test_snapshot_is_frozen(self):
        eng = make_engine(["wR . ."])
        snap = eng.get_snapshot()
        assert isinstance(snap, GameSnapshot)
        with pytest.raises(Exception):
            snap.game_over = True  # type: ignore

    def test_snapshot_grid_is_immutable_tuple(self):
        eng = make_engine(["wR . ."])
        snap = eng.get_snapshot()
        assert isinstance(snap.grid, tuple)
        assert isinstance(snap.grid[0], tuple)

    def test_snapshot_scores_is_copy(self):
        eng = make_engine(["wR . ."])
        snap = eng.get_snapshot()
        snap.scores["w"] = 999          # mutating the copy must not affect engine
        assert eng.get_snapshot().scores["w"] == 0

    def test_snapshot_reflects_active_motions(self):
        eng = make_engine(["wR . . ."])
        eng.request_move(pos(0, 0), pos(0, 3))
        snap = eng.get_snapshot()
        assert len(snap.active_motions) == 1
        m = snap.active_motions[0]
        assert m.piece == Piece("w", "R")
        assert m.src   == pos(0, 0)
        assert m.dst   == pos(0, 3)

    def test_snapshot_no_active_motions_after_completion(self):
        eng = make_engine(["wR . . ."])
        eng.request_move(pos(0, 0), pos(0, 3))
        eng.tick(3000)                                   # 3 cells * 1000ms
        assert eng.get_snapshot().active_motions == ()

    def test_initial_snapshot_not_game_over(self):
        eng = make_engine(["wK . bK"])
        snap = eng.get_snapshot()
        assert snap.game_over is False
        assert snap.winner is None


class TestLegalDestinations:
    def test_returns_rook_line_moves(self):
        eng = make_engine(["wR . . ."])
        legal = set(eng.get_legal_destinations(pos(0, 0)))
        assert legal == {pos(0, 1), pos(0, 2), pos(0, 3)}

    def test_returns_empty_when_piece_on_cooldown(self):
        eng = make_engine(["wR . ."])
        eng.request_move(pos(0, 0), pos(0, 1))
        eng.tick(1000)
        assert eng.get_legal_destinations(pos(0, 1)) == ()

    def test_returns_empty_when_source_empty(self):
        eng = make_engine([". . ."])
        assert eng.get_legal_destinations(pos(0, 0)) == ()


# ── dependency injection ───────────────────────────────────────────────

class TestDependencyInjection:
    def test_accepts_injected_dependencies(self):
        board   = Board(["wR . ."])
        arbiter = RealTimeArbiter(board)
        engine  = GameEngine(board, RuleEngine(), arbiter)
        assert engine.get_snapshot().game_over is False

    def test_shared_board_reflects_engine_changes(self):
        board   = Board(["wR . ."])
        arbiter = RealTimeArbiter(board)
        engine  = GameEngine(board, RuleEngine(), arbiter)
        engine.request_move(pos(0, 0), pos(0, 2))
        engine.tick(2000)                                # 2 cells * 1000ms
        assert board.get_piece(pos(0, 2)) == Piece("w", "R")
