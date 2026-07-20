from engine.game_engine import RequestMoveResult
from engine.models.board import Board
from engine.models.position import Position
from engine.rules.rule_engine import RuleEngine
from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.game_engine import GameEngine
from engine.config import DEFAULT_CONFIG
from ui.interaction.board_mapper import BoardMapper
from ui.interaction.controller import Controller, ControllerOutcomeAdapter
from ui.state.outcome import ActionOutcome


def _build_controller(board_lines: list[str]) -> tuple[Controller, GameEngine]:
    board = Board(board_lines)
    engine = GameEngine(board, RuleEngine(), RealTimeArbiter(board))
    mapper = BoardMapper(cell_size=100, rows=len(board_lines), cols=len(board_lines[0].split()))
    return Controller(engine, mapper), engine


class _ControllerStub:
    def __init__(self, result):
        self._result = result
        self.pending_src = None

    def on_click(self, x: int, y: int):
        _ = (x, y)
        return self._result


def test_first_click_on_empty_cell_does_not_select_source() -> None:
    """Verify first click on empty cell does not select source."""
    controller, _engine = _build_controller([
        "wR . .",
        ". . .",
        ". . .",
    ])

    result = controller.on_click(150, 150)

    assert result is None
    assert controller.pending_src is None


def test_stale_selection_is_recovered_instead_of_requesting_empty_source() -> None:
    """Verify stale selection is recovered instead of requesting empty source."""
    controller, engine = _build_controller(["wR . ."])

    # Select rook and start a move.
    assert controller.on_click(50, 50) is None
    assert controller.on_click(250, 50) == RequestMoveResult.ACCEPTED

    # Click the old source while rook is in flight: should not attempt EMPTY_SOURCE move.
    assert controller.on_click(50, 50) is None

    # Next click on destination while moving should be treated as a normal action and not EMPTY_SOURCE.
    result = controller.on_click(150, 50)
    assert result in (None, RequestMoveResult.PIECE_BUSY)

    # Complete first motion; while cooldown is active, selecting that piece does nothing.
    engine.tick(2000)
    assert controller.on_click(250, 50) is None
    result_after_arrival = controller.on_click(150, 50)
    assert result_after_arrival is None
    assert controller.pending_src is None

    # After cooldown, the next move should be accepted.
    engine.tick(DEFAULT_CONFIG.cooldown_ms)
    assert controller.on_click(250, 50) is None
    assert controller.on_click(150, 50) == RequestMoveResult.ACCEPTED


def test_click_on_frozen_piece_does_not_store_pending_move() -> None:
    """Verify click on frozen piece does not store pending move."""
    controller, engine = _build_controller(["wR . ."])

    # Move rook to the last cell.
    assert controller.on_click(50, 50) is None
    assert controller.on_click(250, 50) == RequestMoveResult.ACCEPTED
    engine.tick(2000)

    # While cooldown is active, clicking the piece should do nothing.
    assert controller.on_click(250, 50) is None
    assert controller.pending_src is None

    # A destination click alone should still do nothing (no hidden queued source).
    assert controller.on_click(150, 50) is None
    assert controller.pending_src is None

    # After cooldown, move must require a fresh two-click action.
    engine.tick(DEFAULT_CONFIG.cooldown_ms)
    assert controller.on_click(150, 50) is None
    assert controller.on_click(250, 50) is None
    assert controller.on_click(50, 50) == RequestMoveResult.ACCEPTED


def test_outcome_adapter_returns_none_when_controller_returns_none() -> None:
    """Verify outcome adapter returns none when controller returns none."""
    adapter = ControllerOutcomeAdapter(_ControllerStub(None))
    assert adapter.on_click(1, 2) is None


def test_outcome_adapter_maps_accept_to_success_outcome() -> None:
    """Verify outcome adapter maps accept to success outcome."""
    adapter = ControllerOutcomeAdapter(_ControllerStub(RequestMoveResult.ACCEPTED))
    assert adapter.on_click(1, 2) == ActionOutcome.ok()


def test_outcome_adapter_maps_failure_to_failed_outcome() -> None:
    """Verify outcome adapter maps failure to failed outcome."""
    adapter = ControllerOutcomeAdapter(_ControllerStub(RequestMoveResult.ILLEGAL_PIECE_MOVE))
    assert adapter.on_click(1, 2) == ActionOutcome.fail(RequestMoveResult.ILLEGAL_PIECE_MOVE)


def test_outcome_adapter_passes_through_action_outcome() -> None:
    """Verify outcome adapter passes through action outcome."""
    expected = ActionOutcome.fail(RequestMoveResult.PIECE_ON_COOLDOWN)
    adapter = ControllerOutcomeAdapter(_ControllerStub(expected))
    assert adapter.on_click(1, 2) == expected
