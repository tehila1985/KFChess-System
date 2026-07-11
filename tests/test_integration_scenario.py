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
    Move:   wR (0,0) → (0,3)   [rook, duration=1000 ms]
    Ticks:  500 ms (in-flight) + 500 ms (arrives)
    Assert: wR is at (0,3), (0,0) is empty, score unchanged.
    """

    def test_rook_moves_to_destination(self):
        engine, ctrl, renderer = build(["wR . . ."])

        print_step("INITIAL STATE", renderer, engine)

        # ── select source ──────────────────────────────────────────────
        result = ctrl.on_click(*px(0, 0))
        assert result is None, "first click should select, not submit"
        assert ctrl.pending_src == Position(0, 0)
        print_step("After selecting wR at (0,0)", renderer, engine)

        # ── submit move ────────────────────────────────────────────────
        result = ctrl.on_click(*px(3, 0))
        assert result == RequestMoveResult.ACCEPTED
        assert ctrl.pending_src is None
        print_step("After requesting move -> (0,3)  [rook in transit]", renderer, engine)

        # source shown at src while in transit; destination not yet set
        snap = engine.get_snapshot()
        assert snap.grid[0][0] == "wR", "src must show piece while in transit"
        assert snap.grid[0][3] == ".", "dst must still be empty before arrival"
        assert len(snap.active_motions) == 1

        # ── partial tick — piece still in flight ───────────────────────
        engine.tick(500)
        print_step("After tick(500) — still in transit", renderer, engine)
        snap = engine.get_snapshot()
        assert snap.grid[0][3] == ".", "piece must not arrive before duration elapses"
        assert len(snap.active_motions) == 1

        # ── final tick — piece arrives ─────────────────────────────────
        engine.tick(1500)
        print_step("After tick(1500) — piece arrived", renderer, engine)
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
    Move:   wR (0,0) → (0,3)   captures bR
    Assert: score["w"] == 5 (rook value), bR gone.
    """

    def test_capture_updates_score(self):
        engine, ctrl, renderer = build(["wR . . bR"])

        print_step("INITIAL STATE", renderer, engine)

        ctrl.on_click(*px(0, 0))
        result = ctrl.on_click(*px(3, 0))
        assert result == RequestMoveResult.ACCEPTED
        print_step("Move requested — wR targeting bR", renderer, engine)

        engine.tick(2000)
        print_step("After tick(2000) — capture resolved", renderer, engine)

        snap = engine.get_snapshot()
        assert snap.grid[0][3] == "wR",  "wR must occupy the captured square"
        assert snap.scores["w"] == 5,    "white scores 5 for capturing a rook"
        assert snap.scores["b"] == 0
        assert snap.game_over is False


# ── Scenario 3: king capture ends the game ────────────────────────────

class TestScenarioKingCapture:
    """
    Board:  wR . bK
    Move:   wR (0,0) → (0,2)   captures bK
    Assert: game_over=True, winner='w'.
    """

    def test_king_capture_ends_game(self):
        engine, ctrl, renderer = build(["wR . bK"])

        print_step("INITIAL STATE", renderer, engine)

        ctrl.on_click(*px(0, 0))
        result = ctrl.on_click(*px(2, 0))
        assert result == RequestMoveResult.ACCEPTED
        print_step("wR targeting bK", renderer, engine)

        engine.tick(2000)
        print_step("After tick(2000) — king captured", renderer, engine)

        snap = engine.get_snapshot()
        assert snap.game_over is True
        assert snap.winner == "w"
        assert "GAME OVER" in renderer.render(snap)

    def test_no_moves_accepted_after_game_over(self):
        engine, ctrl, renderer = build(["wR . bK"])

        ctrl.on_click(*px(0, 0))
        ctrl.on_click(*px(2, 0))
        engine.tick(2000)

        # try to move the winning rook — must be rejected
        ctrl.on_click(*px(2, 0))
        result = ctrl.on_click(*px(1, 0))
        assert result == RequestMoveResult.GAME_OVER
        print_step("Move rejected after game over", renderer, engine)


# ── Scenario 4: piece-busy rejection ─────────────────────────────────

class TestScenarioPieceBusy:
    """
    Board:  wR . . .
    Move 1: wR (0,0) → (0,3)   accepted
    Move 2: same piece again    rejected as PIECE_BUSY
    """

    def test_busy_piece_cannot_move_again(self):
        """
        Once start_motion fires, the arbiter clears the source square.
        Clicking that empty square returns EMPTY_SOURCE — the piece is
        unreachable for a second command while it is in transit.
        PIECE_BUSY is the engine-level guard; EMPTY_SOURCE is what the
        rule-engine sees when the board square is already cleared.
        Both prove the piece cannot be commanded twice mid-flight.
        """
        engine, ctrl, renderer = build(["wR . . ."])

        print_step("INITIAL STATE", renderer, engine)

        ctrl.on_click(*px(0, 0))
        r1 = ctrl.on_click(*px(3, 0))
        assert r1 == RequestMoveResult.ACCEPTED
        print_step("First move accepted - wR in transit", renderer, engine)

        # src is now empty on the board, but the engine still tracks the
        # motion by its original src position -> PIECE_BUSY fires first
        ctrl.on_click(*px(0, 0))
        r2 = ctrl.on_click(*px(1, 0))
        assert r2 == RequestMoveResult.PIECE_BUSY
        print_step("Second command on in-transit piece rejected (PIECE_BUSY)", renderer, engine)

        # complete the original motion
        engine.tick(2000)
        print_step("After tick(2000) - original move completed", renderer, engine)
        snap = engine.get_snapshot()
        assert snap.grid[0][3] == "wR"


# ── Scenario 5: two pieces move concurrently ─────────────────────────

class TestScenarioConcurrentMoves:
    """
    Board:  wR . . bR
            .  . .  .
    Both pieces move toward each other's starting column simultaneously.
    wR (0,0)→(0,2)  and  bR (0,3)→(0,1) — they do NOT swap squares
    so there is no head-to-head; both land independently.
    """

    def test_two_pieces_move_concurrently(self):
        engine, ctrl, renderer = build(["wR . . bR", ". . . ."])

        print_step("INITIAL STATE", renderer, engine)

        # move wR
        ctrl.on_click(*px(0, 0))
        r1 = ctrl.on_click(*px(2, 0))
        assert r1 == RequestMoveResult.ACCEPTED

        # move bR
        ctrl.on_click(*px(3, 0))
        r2 = ctrl.on_click(*px(1, 0))
        assert r2 == RequestMoveResult.ACCEPTED

        snap = engine.get_snapshot()
        assert len(snap.active_motions) == 2
        print_step("Both pieces in transit", renderer, engine)

        engine.tick(2000)
        print_step("After tick(2000) — both arrived", renderer, engine)

        snap = engine.get_snapshot()
        assert snap.grid[0][2] == "wR", "wR must be at (0,2)"
        assert snap.grid[0][1] == "bR", "bR must be at (0,1)"
        assert len(snap.active_motions) == 0


# ── Scenario 6: pawn move (shorter duration) ─────────────────────────

class TestScenarioPawnMove:
    """
    Board:  .  .  .
            .  .  .
            .  .  .
            . wP  .    ← white pawn at start row (row 3 of 4-row board)
    Pawn duration = 500 ms.
    Move: wP (3,1) → (2,1)  one step forward.
    """

    def test_pawn_arrives_after_500ms(self):
        engine, ctrl, renderer = build([
            ". . .",
            ". . .",
            ". . .",
            ". wP .",
        ])

        print_step("INITIAL STATE", renderer, engine)

        ctrl.on_click(*px(1, 3))          # select wP at col=1, row=3
        result = ctrl.on_click(*px(1, 2)) # move to row=2
        assert result == RequestMoveResult.ACCEPTED
        print_step("Pawn move requested", renderer, engine)

        engine.tick(250)
        print_step("After tick(250) — pawn still in transit", renderer, engine)
        assert engine.get_snapshot().grid[2][1] == "."

        engine.tick(250)
        print_step("After tick(250) — pawn arrived", renderer, engine)
        snap = engine.get_snapshot()
        assert snap.grid[3][1] == ".",   "src must be empty"
        assert snap.grid[2][1] == "wP",  "pawn must be at destination"
