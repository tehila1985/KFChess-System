"""
Integration scenarios — full pipeline: Mapper → Controller → GameEngine
                                        → RealTimeArbiter → TextRenderer

No time.sleep anywhere. Time advances exclusively through engine.tick().
Each test prints the board at every meaningful step so the output is
visually verifiable when running with `pytest -s`.
"""
import pytest
from engine.models.board import Board
from engine.models.piece import Piece
from engine.models.position import Position
from engine.rules.rule_engine import RuleEngine
from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.game_engine import GameEngine, RequestMoveResult
from ui.board_mapper import BoardMapper
from ui.controller import Controller
from ui.text_renderer import TextRenderer


# ── shared wiring helper ───────────────────────────────────────────────

CELL = 100   # pixels per cell used in every scenario

def build(board_lines: list[str]):
    """Wire all components and return (engine, controller, renderer)."""
    board      = Board(board_lines)
    arbiter    = RealTimeArbiter(board)
    engine     = GameEngine(board, RuleEngine(), arbiter)
    mapper     = BoardMapper(cell_size=CELL, rows=len(board_lines), cols=len(board_lines[0].split()))
    controller = Controller(engine, mapper)
    renderer   = TextRenderer()
    return engine, controller, renderer


def px(col: int, row: int) -> tuple[int, int]:
    """Centre pixel of a grid cell — avoids off-by-one on cell boundaries."""
    return col * CELL + CELL // 2, row * CELL + CELL // 2


def print_step(label: str, renderer: TextRenderer, engine: GameEngine) -> None:
    snap = engine.get_snapshot()
    print(f"\n{'-' * 40}")
    print(f"  {label}")
    print('-' * 40)
    print(renderer.render(snap))


# ── Scenario 1: simple rook move, no capture ──────────────────────────

class TestScenarioRookMove:
    """
    Board:  wR . . .
    Move:   wR (0,0) → (0,3)   [rook, 3 cells * 1000ms = 3000ms]
    """

    def test_rook_moves_to_destination(self):
        engine, ctrl, renderer = build(["wR . . ."])

        print_step("INITIAL STATE", renderer, engine)

        result = ctrl.on_click(*px(0, 0))
        assert result is None, "first click should select, not submit"
        assert ctrl.pending_src == Position(0, 0)

        result = ctrl.on_click(*px(3, 0))
        assert result == RequestMoveResult.ACCEPTED
        assert ctrl.pending_src is None

        snap = engine.get_snapshot()
        assert snap.grid[0][0] == "wR", "src must show piece while in transit"
        assert snap.grid[0][3] == ".", "dst must still be empty before arrival"
        assert len(snap.active_motions) == 1

        engine.tick(500)
        snap = engine.get_snapshot()
        assert snap.grid[0][3] == ".", "piece must not arrive before duration elapses"
        assert len(snap.active_motions) == 1

        engine.tick(2500)   # total 3000ms = 3 cells * 1000ms
        print_step("After tick(3000) — piece arrived", renderer, engine)
        snap = engine.get_snapshot()
        assert snap.grid[0][0] == ".",   "src must remain empty after arrival"
        assert snap.grid[0][3] == "wR",  "wR must be at destination"
        assert len(snap.active_motions) == 0
        assert snap.scores["w"] == 0,    "no capture — score must be zero"
        assert snap.game_over is False


# ── Scenario 2: capture — rook takes enemy rook, score updated ─────────

class TestScenarioCapture:
    """
    Board:  wR . . bR
    Move:   wR (0,0) → (0,3)   captures bR  [3 cells * 1000ms = 3000ms]
    """

    def test_capture_updates_score(self):
        engine, ctrl, renderer = build(["wR . . bR"])

        ctrl.on_click(*px(0, 0))
        result = ctrl.on_click(*px(3, 0))
        assert result == RequestMoveResult.ACCEPTED

        engine.tick(3000)   # 3 cells * 1000ms
        snap = engine.get_snapshot()
        assert snap.grid[0][3] == "wR"
        assert snap.scores["w"] == 5
        assert snap.scores["b"] == 0
        assert snap.game_over is False


# ── Scenario 3: king capture ends the game ────────────────────────────

class TestScenarioKingCapture:
    """
    Board:  wR . bK
    Move:   wR (0,0) → (0,2)   captures bK  [2 cells * 1000ms = 2000ms]
    """

    def test_king_capture_ends_game(self):
        engine, ctrl, renderer = build(["wR . bK"])

        ctrl.on_click(*px(0, 0))
        result = ctrl.on_click(*px(2, 0))
        assert result == RequestMoveResult.ACCEPTED

        engine.tick(2000)   # 2 cells * 1000ms
        snap = engine.get_snapshot()
        assert snap.game_over is True
        assert snap.winner == "w"
        assert "GAME OVER" in renderer.render(snap)

    def test_no_moves_accepted_after_game_over(self):
        engine, ctrl, renderer = build(["wR . bK"])
        ctrl.on_click(*px(0, 0))
        ctrl.on_click(*px(2, 0))
        engine.tick(2000)   # 2 cells * 1000ms

        ctrl.on_click(*px(2, 0))
        result = ctrl.on_click(*px(1, 0))
        assert result == RequestMoveResult.GAME_OVER


# ── Scenario 4: piece-busy rejection ─────────────────────────────────

class TestScenarioPieceBusy:
    """
    Board:  wR . . .
    Move 1: wR (0,0) → (0,3)   accepted  [3 cells * 1000ms = 3000ms]
    Move 2: same piece again    rejected as PIECE_BUSY
    """

    def test_busy_piece_cannot_move_again(self):
        engine, ctrl, renderer = build(["wR . . ."])

        ctrl.on_click(*px(0, 0))
        r1 = ctrl.on_click(*px(3, 0))
        assert r1 == RequestMoveResult.ACCEPTED

        ctrl.on_click(*px(0, 0))
        r2 = ctrl.on_click(*px(1, 0))
        assert r2 == RequestMoveResult.PIECE_BUSY

        engine.tick(3000)   # 3 cells * 1000ms
        snap = engine.get_snapshot()
        assert snap.grid[0][3] == "wR"


# ── Scenario 5: two pieces move concurrently ─────────────────────────

class TestScenarioConcurrentMoves:
    """
    Board:  wR . . bR
    wR (0,0)→(0,2)  and  bR (0,3)→(0,1)  [2 cells * 1000ms = 2000ms]
    """

    def test_two_pieces_move_concurrently(self):
        engine, ctrl, renderer = build(["wR . . bR", ". . . ."])

        ctrl.on_click(*px(0, 0))
        r1 = ctrl.on_click(*px(2, 0))
        assert r1 == RequestMoveResult.ACCEPTED

        ctrl.on_click(*px(3, 0))
        r2 = ctrl.on_click(*px(1, 0))
        assert r2 == RequestMoveResult.ACCEPTED

        snap = engine.get_snapshot()
        assert len(snap.active_motions) == 2

        engine.tick(2000)   # 2 cells * 1000ms
        snap = engine.get_snapshot()
        assert snap.grid[0][2] == "wR"
        assert snap.grid[0][1] == "bR"
        assert len(snap.active_motions) == 0


# ── Scenario 6: pawn move (shorter duration) ─────────────────────────

class TestScenarioPawnMove:
    """
    Board:  . . .
            . . .
            . . .
            . wP .
    Pawn: 1 cell * 500ms = 500ms
    """

    def test_pawn_arrives_after_500ms(self):
        engine, ctrl, renderer = build([
            ". . .",
            ". . .",
            ". . .",
            ". wP .",
        ])

        ctrl.on_click(*px(1, 3))
        result = ctrl.on_click(*px(1, 2))
        assert result == RequestMoveResult.ACCEPTED

        engine.tick(250)
        assert engine.get_snapshot().grid[2][1] == "."

        engine.tick(250)   # total 500ms = 1 cell * 500ms
        snap = engine.get_snapshot()
        assert snap.grid[3][1] == ".",   "src must be empty"
        assert snap.grid[2][1] == "wP",  "pawn must be at destination"
