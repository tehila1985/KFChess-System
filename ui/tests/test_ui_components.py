from engine.models.piece import Piece
from engine.models.position import Position
from ui.state.game_events import GameOver, MoveAccepted, PieceCaptured
from ui.state.observer import EventBus
from ui.ui_components.banner import Banner
from ui.ui_components.moves_feed import MovesFeed
from ui.ui_components.score_panel import ScorePanel


def test_moves_feed_appends_on_move_accepted() -> None:
    bus = EventBus()
    feed = MovesFeed()
    feed.bind(bus)

    bus.publish(MoveAccepted(src=Position(0, 0), dst=Position(0, 3)))

    assert feed.entries == ["Position(row=0, col=0) -> Position(row=0, col=3)"]


def test_score_panel_counts_captures_by_side() -> None:
    bus = EventBus()
    panel = ScorePanel()
    panel.bind(bus)

    bus.publish(PieceCaptured(captured=Piece("w", "P"), at=Position(1, 1)))
    bus.publish(PieceCaptured(captured=Piece("b", "N"), at=Position(2, 2)))

    assert panel.black_captures == 1
    assert panel.white_captures == 1


def test_banner_updates_on_game_over() -> None:
    bus = EventBus()
    banner = Banner()
    banner.bind(bus)

    bus.publish(GameOver(winner="w"))

    assert banner.message == "Game Over - winner: w"
