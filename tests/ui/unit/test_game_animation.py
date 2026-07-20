"""Unit tests for GameAnimationController pub/sub subscriber."""
from __future__ import annotations

from engine.models.position import Position
from ui.config.app_config import AppConfig, UiAnimationConfig
from ui.state.game_events import GameOver, GameStarted, PieceCaptured
from ui.state.observer import EventBus
from ui.ui_components.game_animation import CaptureFlash, GameAnimationController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctrl(
    fade_ms: int = 400,
    hold_ms: int = 1000,
    flash_ms: int = 200,
) -> GameAnimationController:
    cfg = AppConfig(animation=UiAnimationConfig(
        game_start_fade_in_ms=fade_ms,
        game_over_hold_ms=hold_ms,
        capture_flash_ms=flash_ms,
    ))
    return GameAnimationController(_config=cfg.animation)


def _captured(row: int = 3, col: int = 3) -> PieceCaptured:
    return PieceCaptured(
        captured_side="b", captured_type="P",
        points=1, at=Position(row, col),
    )


# ---------------------------------------------------------------------------
# GameStarted → fade-in
# ---------------------------------------------------------------------------

def test_game_started_sets_fading_in() -> None:
    ctrl = _make_ctrl(fade_ms=400)
    bus = EventBus()
    ctrl.bind(bus)

    bus.publish(GameStarted())

    assert ctrl.state.fading_in is True
    assert ctrl.state.fade_alpha == 0.0


def test_fade_in_advances_on_tick() -> None:
    ctrl = _make_ctrl(fade_ms=400)
    bus = EventBus()
    ctrl.bind(bus)
    bus.publish(GameStarted())

    ctrl.tick(200)  # half of 400 ms

    assert 0.4 < ctrl.state.fade_alpha < 0.6
    assert ctrl.state.fading_in is True


def test_fade_in_completes_when_elapsed_exceeds_duration() -> None:
    ctrl = _make_ctrl(fade_ms=400)
    bus = EventBus()
    ctrl.bind(bus)
    bus.publish(GameStarted())

    ctrl.tick(400)

    assert ctrl.state.fade_alpha == 1.0
    assert ctrl.state.fading_in is False


def test_fade_alpha_does_not_exceed_one() -> None:
    ctrl = _make_ctrl(fade_ms=100)
    bus = EventBus()
    ctrl.bind(bus)
    bus.publish(GameStarted())

    ctrl.tick(9999)

    assert ctrl.state.fade_alpha == 1.0


# ---------------------------------------------------------------------------
# GameOver → hold state
# ---------------------------------------------------------------------------

def test_game_over_activates_hold() -> None:
    ctrl = _make_ctrl(hold_ms=1000)
    bus = EventBus()
    ctrl.bind(bus)

    bus.publish(GameOver(winner="w"))

    assert ctrl.state.game_over_active is True
    assert ctrl.state.game_over_remaining_ms == 1000


def test_game_over_hold_counts_down() -> None:
    ctrl = _make_ctrl(hold_ms=1000)
    bus = EventBus()
    ctrl.bind(bus)
    bus.publish(GameOver(winner="w"))

    ctrl.tick(300)

    assert ctrl.state.game_over_remaining_ms == 700
    assert ctrl.state.game_over_active is True


def test_game_over_hold_deactivates_when_expired() -> None:
    ctrl = _make_ctrl(hold_ms=500)
    bus = EventBus()
    ctrl.bind(bus)
    bus.publish(GameOver(winner="w"))

    ctrl.tick(500)

    assert ctrl.state.game_over_remaining_ms == 0
    assert ctrl.state.game_over_active is False


# ---------------------------------------------------------------------------
# PieceCaptured → capture flash
# ---------------------------------------------------------------------------

def test_capture_adds_flash() -> None:
    ctrl = _make_ctrl(flash_ms=200)
    bus = EventBus()
    ctrl.bind(bus)

    bus.publish(_captured(row=2, col=5))

    assert len(ctrl.state.capture_flashes) == 1
    flash = ctrl.state.capture_flashes[0]
    assert flash.row == 2
    assert flash.col == 5
    assert flash.remaining_ms == 200


def test_multiple_captures_add_multiple_flashes() -> None:
    ctrl = _make_ctrl(flash_ms=200)
    bus = EventBus()
    ctrl.bind(bus)

    bus.publish(_captured(row=0, col=0))
    bus.publish(_captured(row=7, col=7))

    assert len(ctrl.state.capture_flashes) == 2


def test_flash_countdown_removes_expired() -> None:
    ctrl = _make_ctrl(flash_ms=100)
    bus = EventBus()
    ctrl.bind(bus)
    bus.publish(_captured())

    ctrl.tick(100)

    assert ctrl.state.capture_flashes == []


def test_flash_partial_countdown_keeps_flash() -> None:
    ctrl = _make_ctrl(flash_ms=200)
    bus = EventBus()
    ctrl.bind(bus)
    bus.publish(_captured())

    ctrl.tick(100)

    assert len(ctrl.state.capture_flashes) == 1
    assert ctrl.state.capture_flashes[0].remaining_ms == 100


# ---------------------------------------------------------------------------
# bind / unbind
# ---------------------------------------------------------------------------

def test_bind_subscribes_three_event_types() -> None:
    ctrl = _make_ctrl()
    bus = EventBus()
    ctrl.bind(bus)

    event_types = {s.event_type for s in ctrl._subscriptions}
    assert event_types == {GameStarted, GameOver, PieceCaptured}


def test_unbind_removes_all_subscriptions() -> None:
    ctrl = _make_ctrl()
    bus = EventBus()
    ctrl.bind(bus)
    ctrl.unbind(bus)

    assert ctrl._subscriptions == []
    for et in (GameStarted, GameOver, PieceCaptured):
        assert bus._subscribers.get(et, []) == []


# ---------------------------------------------------------------------------
# GameFacade publishes GameStarted on first tick
# ---------------------------------------------------------------------------

def test_game_facade_publishes_game_started_on_first_tick() -> None:
    """Integration smoke-test: GameFacade fires GameStarted exactly once."""
    from engine.arbiter.real_time_arbiter import RealTimeArbiter
    from engine.game_engine import GameEngine
    from engine.models.board import Board
    from engine.rules.rule_engine import RuleEngine
    from ui.state.game_facade import GameFacade

    board_lines = [
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
    ]
    board = Board(board_lines)
    engine = GameEngine(board, RuleEngine(), RealTimeArbiter(board))
    facade = GameFacade(engine)

    fired: list[GameStarted] = []
    facade.subject.subscribe(GameStarted, fired.append)

    facade.tick(16)
    assert len(fired) == 1

    facade.tick(16)
    assert len(fired) == 1  # not published again
