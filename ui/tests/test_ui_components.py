from engine.models.piece import Piece
from engine.models.position import Position
from ui.state.game_events import GameOver, MoveAccepted, PieceCaptured
from ui.state.observer import EventBus
from ui.ui_components.banner import Banner
from ui.ui_components.moves_feed import MovesFeed
from ui.ui_components.score_panel import ScorePanel
from ui.state.game_facade import GameFacade
from engine.models.board import Board
from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.game_engine import GameEngine, RequestMoveResult
from engine.rules.rule_engine import RuleEngine


def test_moves_feed_appends_on_move_accepted() -> None:
    bus = EventBus()
    feed = MovesFeed()
    feed.bind(bus)

    bus.publish(MoveAccepted(side="w", piece_type="P", at_ms=36200, src=Position(1, 6), dst=Position(2, 6)))

    assert feed.entries == ["Pg7-g6 [36.2s]"]
    assert feed.white_entries == ["Pg7-g6 [36.2s]"]
    assert feed.black_entries == []


def test_score_panel_counts_captures_by_side() -> None:
    bus = EventBus()
    panel = ScorePanel()
    panel.bind(bus)

    bus.publish(PieceCaptured(captured=Piece("w", "P"), at=Position(1, 1)))
    bus.publish(PieceCaptured(captured=Piece("b", "N"), at=Position(2, 2)))

    assert panel.black_captures == 1
    assert panel.white_captures == 1

def test_score_panel_updates_after_real_capture_from_facade_tick() -> None:
    board = Board(["wR . . bR"])
    engine = GameEngine(board, RuleEngine(), RealTimeArbiter(board))
    facade = GameFacade(engine)
    panel = ScorePanel()
    panel.bind(facade.subject)

    result = facade.request_move(Position(0, 0), Position(0, 3))
    assert result == RequestMoveResult.ACCEPTED

    facade.tick(3000)

    assert panel.white_captures == 1
    assert panel.black_captures == 0


def test_banner_updates_on_game_over() -> None:
    bus = EventBus()
    banner = Banner()
    banner.bind(bus)

    bus.publish(GameOver(winner="w"))

    assert banner.message == "Game Over - winner: w"
