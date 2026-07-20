from server.arbiter.real_time_arbiter import RealTimeArbiter
from server.game_engine import GameEngine, RequestMoveResult
from server.models.board import Board
from server.models.position import Position
from server.rules.rule_engine import RuleEngine
from ui.state.game_events import GameOver, MoveAccepted, MoveRejected
from ui.state.game_facade import GameFacade
from ui.state.outcome import ActionOutcome


def _facade(board_lines: list[str]) -> GameFacade:
    board = Board(board_lines)
    engine = GameEngine(board, RuleEngine(), RealTimeArbiter(board))
    return GameFacade(engine)


def test_request_move_publishes_move_accepted() -> None:
    """Verify request move publishes move accepted."""
    facade = _facade(["wR . . ."])
    events: list[MoveAccepted] = []
    facade.subject.subscribe(MoveAccepted, lambda event: events.append(event))

    result = facade.request_move(Position(0, 0), Position(0, 3))

    assert result == ActionOutcome.ok()
    assert len(events) == 1
    assert events[0].side == "w"
    assert events[0].piece_type == "R"
    assert events[0].at_ms == 0
    assert events[0].src == Position(0, 0)
    assert events[0].dst == Position(0, 3)


def test_request_move_publishes_move_rejected() -> None:
    """Verify request move publishes move rejected."""
    facade = _facade(["wR . .", ". . .", ". . ."])
    events: list[MoveRejected] = []
    facade.subject.subscribe(MoveRejected, lambda event: events.append(event))

    result = facade.request_move(Position(0, 0), Position(2, 2))

    assert result == ActionOutcome.fail(RequestMoveResult.ILLEGAL_PIECE_MOVE)
    assert len(events) == 1
    assert events[0].reason == RequestMoveResult.ILLEGAL_PIECE_MOVE


def test_tick_publishes_game_over_once() -> None:
    """Verify tick publishes game over once."""
    facade = _facade(["wR . bK"])
    events: list[GameOver] = []
    facade.subject.subscribe(GameOver, lambda event: events.append(event))

    assert facade.request_move(Position(0, 0), Position(0, 2)) == ActionOutcome.ok()

    facade.tick(2000)
    facade.tick(2000)

    assert len(events) == 1
    assert events[0].winner == "w"
