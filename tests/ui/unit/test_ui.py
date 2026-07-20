import pytest
from engine.models.board import Board
from engine.models.piece import Piece
from engine.models.position import Position
from engine.rules.rule_engine import RuleEngine
from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.game_engine import GameEngine, RequestMoveResult
from ui.interaction.board_mapper import BoardMapper
from ui.interaction.controller import Controller
from ui.rendering.renderers import TextRenderer


# ── helpers ────────────────────────────────────────────────────────────

def make_engine(board_lines: list[str]) -> GameEngine:
    board   = Board(board_lines)
    arbiter = RealTimeArbiter(board)
    return GameEngine(board, RuleEngine(), arbiter)


def make_controller(engine: GameEngine, cell_size=100, rows=8, cols=8) -> Controller:
    return Controller(engine, BoardMapper(cell_size, rows, cols))


# ── BoardMapper ────────────────────────────────────────────────────────

class TestBoardMapper:
    def mapper(self):
        return BoardMapper(cell_size=100, rows=8, cols=8)

    def test_origin_maps_to_0_0(self):
        """Verify origin maps to 0 0."""
        assert self.mapper().to_position(0, 0) == Position(0, 0)

    def test_center_of_first_cell(self):
        """Verify center of first cell."""
        assert self.mapper().to_position(50, 50) == Position(0, 0)

    def test_second_col_first_row(self):
        """Verify second col first row."""
        assert self.mapper().to_position(100, 0) == Position(0, 1)

    def test_second_row_first_col(self):
        """Verify second row first col."""
        assert self.mapper().to_position(0, 100) == Position(1, 0)

    def test_arbitrary_cell(self):
        """Verify arbitrary cell."""
        assert self.mapper().to_position(350, 250) == Position(2, 3)

    def test_last_valid_cell(self):
        """Verify last valid cell."""
        assert self.mapper().to_position(799, 799) == Position(7, 7)

    def test_negative_x_returns_none(self):
        """Verify negative x returns none."""
        assert self.mapper().to_position(-1, 0) is None

    def test_negative_y_returns_none(self):
        """Verify negative y returns none."""
        assert self.mapper().to_position(0, -1) is None

    def test_x_beyond_grid_returns_none(self):
        """Verify x beyond grid returns none."""
        assert self.mapper().to_position(800, 0) is None

    def test_y_beyond_grid_returns_none(self):
        """Verify y beyond grid returns none."""
        assert self.mapper().to_position(0, 800) is None

    def test_custom_cell_size(self):
        """Verify custom cell size."""
        m = BoardMapper(cell_size=50, rows=4, cols=4)
        assert m.to_position(75, 125) == Position(2, 1)

    def test_exact_boundary_is_next_cell(self):
        """Verify exact boundary is next cell."""
        # pixel 100 is the start of col 1, not the end of col 0
        assert self.mapper().to_position(100, 0) == Position(0, 1)


# ── Controller ─────────────────────────────────────────────────────────

class TestController:
    def test_first_click_returns_none(self):
        """Verify first click returns none."""
        eng  = make_engine(["wR . . .", ". . . .", ". . . .", ". . . ."])
        ctrl = make_controller(eng, cell_size=100, rows=4, cols=4)
        result = ctrl.on_click(0, 0)
        assert result is None

    def test_first_click_sets_pending_src(self):
        """Verify first click sets pending src."""
        eng  = make_engine(["wR . . .", ". . . .", ". . . .", ". . . ."])
        ctrl = make_controller(eng, cell_size=100, rows=4, cols=4)
        ctrl.on_click(0, 0)
        assert ctrl.pending_src == Position(0, 0)

    def test_second_click_returns_result(self):
        """Verify second click returns result."""
        eng  = make_engine(["wR . . .", ". . . .", ". . . .", ". . . ."])
        ctrl = make_controller(eng, cell_size=100, rows=4, cols=4)
        ctrl.on_click(0, 0)
        result = ctrl.on_click(300, 0)
        assert isinstance(result, RequestMoveResult)

    def test_second_click_clears_pending_src(self):
        """Verify second click clears pending src."""
        eng  = make_engine(["wR . . .", ". . . .", ". . . .", ". . . ."])
        ctrl = make_controller(eng, cell_size=100, rows=4, cols=4)
        ctrl.on_click(0, 0)
        ctrl.on_click(300, 0)
        assert ctrl.pending_src is None

    def test_valid_move_accepted(self):
        """Verify valid move accepted."""
        eng  = make_engine(["wR . . .", ". . . .", ". . . .", ". . . ."])
        ctrl = make_controller(eng, cell_size=100, rows=4, cols=4)
        ctrl.on_click(0, 0)                  # select wR at (0,0)
        result = ctrl.on_click(300, 0)       # move to (0,3)
        assert result == RequestMoveResult.ACCEPTED

    def test_invalid_move_returns_error(self):
        """Verify invalid move returns error."""
        eng  = make_engine(["wR . . .", ". . . .", ". . . .", ". . . ."])
        ctrl = make_controller(eng, cell_size=100, rows=4, cols=4)
        ctrl.on_click(0, 0)                  # select wR at (0,0)
        result = ctrl.on_click(100, 100)     # (1,1) — diagonal, illegal for rook
        assert result == RequestMoveResult.ILLEGAL_PIECE_MOVE

    def test_out_of_bounds_click_cancels_selection(self):
        """Verify out of bounds click cancels selection."""
        eng  = make_engine(["wR . . .", ". . . .", ". . . .", ". . . ."])
        ctrl = make_controller(eng, cell_size=100, rows=4, cols=4)
        ctrl.on_click(0, 0)
        ctrl.on_click(9999, 9999)            # out of bounds
        assert ctrl.pending_src is None

    def test_out_of_bounds_first_click_no_selection(self):
        """Verify out of bounds first click no selection."""
        eng  = make_engine(["wR . . .", ". . . .", ". . . .", ". . . ."])
        ctrl = make_controller(eng, cell_size=100, rows=4, cols=4)
        ctrl.on_click(9999, 0)
        assert ctrl.pending_src is None

    def test_controller_holds_no_chess_logic(self):
        """Verify controller holds no chess logic."""
        # Controller must delegate entirely to engine — it has no rule attributes
        ctrl = make_controller(make_engine(["wR . ."]), cell_size=100, rows=1, cols=3)
        assert not hasattr(ctrl, '_rules')
        assert not hasattr(ctrl, '_board')


# ── TextRenderer ───────────────────────────────────────────────────────

class TestTextRenderer:
    renderer = TextRenderer()

    def snapshot(self, board_lines, scores=None, game_over=False, winner=None, motions=()):
        from engine.game_engine import GameSnapshot
        board = Board(board_lines)
        grid  = tuple(tuple(row) for row in board._grid)
        return GameSnapshot(
            grid           = grid,
            scores         = tuple(sorted((scores or {"w": 0, "b": 0}).items())),
            game_over      = game_over,
            winner         = winner,
            active_motions = motions,
        )

    def test_renders_board_rows(self):
        """Verify renders board rows."""
        snap   = self.snapshot(["wR . .", ". wK .", ". . bP"])
        output = self.renderer.render(snap)
        lines  = output.splitlines()
        assert lines[0] == "wR . ."
        assert lines[1] == ". wK ."
        assert lines[2] == ". . bP"

    def test_renders_scores(self):
        """Verify renders scores."""
        snap   = self.snapshot(["wR . ."], scores={"w": 5, "b": 3})
        output = self.renderer.render(snap)
        assert "w:5" in output
        assert "b:3" in output

    def test_renders_game_in_progress(self):
        """Verify renders game in progress."""
        snap   = self.snapshot(["wR . ."])
        output = self.renderer.render(snap)
        assert "Game in progress" in output

    def test_renders_game_over(self):
        """Verify renders game over."""
        snap   = self.snapshot(["wR . ."], game_over=True, winner="w")
        output = self.renderer.render(snap)
        assert "GAME OVER" in output
        assert "w" in output

    def test_renders_black_winner(self):
        """Verify renders black winner."""
        snap   = self.snapshot([". . bR"], game_over=True, winner="b")
        output = self.renderer.render(snap)
        assert "b" in output

    def test_single_row_board(self):
        """Verify single row board."""
        snap   = self.snapshot(["wK bK"])
        output = self.renderer.render(snap)
        assert output.startswith("wK bK")

    def test_empty_board_renders_dots(self):
        """Verify empty board renders dots."""
        snap   = self.snapshot([". . .", ". . ."])
        lines  = self.renderer.render(snap).splitlines()
        assert lines[0] == ". . ."
        assert lines[1] == ". . ."

    def test_renderer_returns_string(self):
        """Verify renderer returns string."""
        snap = self.snapshot(["wR . ."])
        assert isinstance(self.renderer.render(snap), str)
