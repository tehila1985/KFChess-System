"""Unit tests for SoundPlayer pub/sub subscriber."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from engine.models.position import Position
from ui.config.app_config import AppConfig, UiSoundConfig, DEFAULT_APP_CONFIG
from ui.state.game_events import GameOver, GameStarted, MoveAccepted, PieceCaptured
from ui.state.observer import EventBus
from ui.ui_components.sound_player import SoundPlayer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(enabled: bool = True) -> SoundPlayer:
    cfg = AppConfig(sound=UiSoundConfig(enabled=enabled))
    return SoundPlayer(_config=cfg.sound, _assets_dir=cfg.assets.assets_dir)


def _accepted() -> MoveAccepted:
    return MoveAccepted(side="w", piece_type="P", at_ms=0,
                        src=Position(6, 4), dst=Position(5, 4))


def _captured() -> PieceCaptured:
    return PieceCaptured(captured_side="b", captured_type="P",
                         points=1, at=Position(5, 4))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sound_player_disabled_never_plays(monkeypatch) -> None:
    """When enabled=False no sound is played regardless of events."""
    played: list[str] = []
    player = _make_player(enabled=False)
    # Inject a fake sound object to ensure _play is never called.
    fake_sound = MagicMock()
    fake_sound.play.side_effect = lambda: played.append("played")
    player._snd_move = fake_sound

    bus = EventBus()
    player.bind(bus)
    bus.publish(_accepted())

    assert played == []


def test_bind_subscribes_to_all_four_events() -> None:
    """bind() registers handlers for all four event types when enabled."""
    bus = EventBus()
    # Use a fresh player with enabled=True but no mixer (sounds stay None).
    player = SoundPlayer(_config=UiSoundConfig(enabled=True),
                         _assets_dir=DEFAULT_APP_CONFIG.assets.assets_dir)
    player.bind(bus)

    # Subscriptions are registered only when enabled.
    # (pygame may not be available in CI, so _ready may be False —
    #  but bind() still registers regardless of _ready when enabled=True.)
    assert len(player._subscriptions) == 4
    event_types = {s.event_type for s in player._subscriptions}
    assert event_types == {GameStarted, MoveAccepted, PieceCaptured, GameOver}


def test_bind_disabled_registers_no_subscriptions() -> None:
    """bind() is a no-op when enabled=False."""
    bus = EventBus()
    player = _make_player(enabled=False)
    player.bind(bus)

    assert player._subscriptions == []


def test_unbind_removes_all_subscriptions() -> None:
    """unbind() removes every subscription from the bus."""
    bus = EventBus()
    player = _make_player(enabled=False)
    player.bind(bus)
    player.unbind(bus)

    assert player._subscriptions == []
    # Bus should now have no subscribers for any of the four event types.
    for et in (GameStarted, MoveAccepted, PieceCaptured, GameOver):
        assert bus._subscribers.get(et, []) == []


def test_move_accepted_calls_play_on_move_sound() -> None:
    """MoveAccepted event triggers the move sound."""
    player = SoundPlayer(_config=UiSoundConfig(enabled=True),
                         _assets_dir=DEFAULT_APP_CONFIG.assets.assets_dir)
    bus = EventBus()
    player.bind(bus)          # registers subscriptions (enabled=True)
    fake = MagicMock()
    player._snd_move = fake   # inject after bind so the handler sees it

    bus.publish(_accepted())

    fake.play.assert_called_once()


def test_piece_captured_calls_play_on_capture_sound() -> None:
    """PieceCaptured event triggers the capture sound."""
    player = SoundPlayer(_config=UiSoundConfig(enabled=True),
                         _assets_dir=DEFAULT_APP_CONFIG.assets.assets_dir)
    bus = EventBus()
    player.bind(bus)
    fake = MagicMock()
    player._snd_capture = fake

    bus.publish(_captured())

    fake.play.assert_called_once()


def test_game_started_calls_play_on_start_sound() -> None:
    """GameStarted event triggers the game-start sound."""
    player = SoundPlayer(_config=UiSoundConfig(enabled=True),
                         _assets_dir=DEFAULT_APP_CONFIG.assets.assets_dir)
    bus = EventBus()
    player.bind(bus)
    fake = MagicMock()
    player._snd_game_start = fake

    bus.publish(GameStarted())

    fake.play.assert_called_once()


def test_game_over_calls_play_on_game_over_sound() -> None:
    """GameOver event triggers the game-over sound."""
    player = SoundPlayer(_config=UiSoundConfig(enabled=True),
                         _assets_dir=DEFAULT_APP_CONFIG.assets.assets_dir)
    bus = EventBus()
    player.bind(bus)
    fake = MagicMock()
    player._snd_game_over = fake

    bus.publish(GameOver(winner="w"))

    fake.play.assert_called_once()


def test_none_sound_does_not_raise() -> None:
    """If a sound file is None, publishing the event must not raise."""
    player = _make_player(enabled=False)
    # All sounds remain None (no files loaded).
    bus = EventBus()
    player.bind(bus)

    bus.publish(GameStarted())
    bus.publish(_accepted())
    bus.publish(_captured())
    bus.publish(GameOver(winner="b"))
    # No exception = pass
