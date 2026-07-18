from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.game_engine import GameEngine, RequestMoveResult
from engine.models.board import Board
from engine.models.position import Position
from engine.rules.rule_engine import RuleEngine
from ui.state.game_events import GameOver, MoveAccepted, MoveRejected
from ui.state.game_facade import GameFacade


def _facade(board_lines: list[str]) -> GameFacade:
    board = Board(board_lines)
    engine = GameEngine(board, RuleEngine(), RealTimeArbiter(board))
    return GameFacade(engine)


def test_request_move_publishes_move_accepted() -> None:
    facade = _facade(["wR . . ."])
    events: list[MoveAccepted] = []
    facade.subject.subscribe(MoveAccepted, lambda event: events.append(event))

    result = facade.request_move(Position(0, 0), Position(0, 3))

    assert result == RequestMoveResult.ACCEPTED
    assert len(events) == 1
    assert events[0].src == Position(0, 0)
    assert events[0].dst == Position(0, 3)


def test_request_move_publishes_move_rejected() -> None:
    facade = _facade(["wR . .", ". . .", ". . ."])
    events: list[MoveRejected] = []
    facade.subject.subscribe(MoveRejected, lambda event: events.append(event))

    result = facade.request_move(Position(0, 0), Position(2, 2))

    assert result == RequestMoveResult.ILLEGAL_PIECE_MOVE
    assert len(events) == 1
    assert events[0].reason == RequestMoveResult.ILLEGAL_PIECE_MOVE


def test_tick_publishes_game_over_once() -> None:
    facade = _facade(["wR . bK"])
    events: list[GameOver] = []
    facade.subject.subscribe(GameOver, lambda event: events.append(event))

    assert facade.request_move(Position(0, 0), Position(0, 2)) == RequestMoveResult.ACCEPTED

    facade.tick(2000)
    facade.tick(2000)

    assert len(events) == 1
    assert events[0].winner == "w"
