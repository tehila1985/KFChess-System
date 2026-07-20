from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ui.config.app_config import DEFAULT_APP_CONFIG, UiSoundConfig
from ui.state.game_events import GameOver, GameStarted, MoveAccepted, PieceCaptured
from ui.state.observer import Subject, Subscription

logger = logging.getLogger(__name__)

# pygame is optional — if not installed the player silently does nothing.
try:
    import pygame  # type: ignore
    _PYGAME_AVAILABLE = True
except ImportError:
    pygame = None  # type: ignore
    _PYGAME_AVAILABLE = False


def _init_mixer() -> bool:
    """Initialise pygame and its mixer. Returns True on success."""
    if not _PYGAME_AVAILABLE:
        return False
    try:
        if not pygame.get_init():
            pygame.init()
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        return True
    except Exception as exc:
        logger.warning("pygame.mixer init failed: %s", exc)
        return False


def _load(path: Path) -> object | None:
    """
    Load a sound file and return a callable play object.

    Supports both WAV (via pygame.mixer.Sound) and MP3/OGG
    (via a thin wrapper around pygame.mixer.music).
    Returns None silently if the file is missing or loading fails.
    """
    if not path.exists():
        logger.debug("Sound file not found, skipping: %s", path)
        return None
    suffix = path.suffix.lower()
    try:
        if suffix in (".mp3", ".ogg", ".flac"):
            return _MusicSound(str(path))
        return pygame.mixer.Sound(str(path))
    except Exception as exc:
        logger.warning("Could not load sound %s: %s", path, exc)
        return None


class _MusicSound:
    """
    Thin wrapper that makes pygame.mixer.music behave like pygame.mixer.Sound.

    pygame.mixer.music streams one file at a time, so calling play() loads
    and starts the track, stopping whatever was playing before.  This is
    acceptable for short one-shot effects.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    def play(self) -> None:
        try:
            pygame.mixer.music.load(self._path)
            pygame.mixer.music.play()
        except Exception as exc:
            logger.debug("Music play failed for %s: %s", self._path, exc)


def _play(sound: object | None) -> None:
    if sound is not None:
        try:
            sound.play()  # type: ignore[union-attr]
        except Exception as exc:
            logger.debug("Sound play failed: %s", exc)


@dataclass
class SoundPlayer:
    """
    Pub/sub subscriber that plays sound effects in response to game events.

    All sound operations are fire-and-forget.  Any missing file or library
    failure is logged at DEBUG/WARNING level and silently ignored so the game
    never crashes due to audio issues.

    Sound files are configured via UiSoundConfig (paths relative to assets_dir).
    Supports WAV, MP3 and OGG.  Set ``sound.enabled = False`` in AppConfig
    to disable all audio.
    """

    _config: UiSoundConfig = field(default_factory=lambda: DEFAULT_APP_CONFIG.sound)
    _assets_dir: Path = field(default_factory=lambda: DEFAULT_APP_CONFIG.assets.assets_dir)

    _snd_move: object | None = field(default=None, init=False)
    _snd_capture: object | None = field(default=None, init=False)
    _snd_game_start: object | None = field(default=None, init=False)
    _snd_game_over: object | None = field(default=None, init=False)

    _subscriptions: list[Subscription] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if not self._config.enabled:
            return
        if not _init_mixer():
            return
        self._snd_move = _load(self._assets_dir / self._config.move_sound) if self._config.move_sound else None
        self._snd_capture = _load(self._assets_dir / self._config.capture_sound) if self._config.capture_sound else None
        self._snd_game_start = _load(self._assets_dir / self._config.game_start_sound) if self._config.game_start_sound else None
        self._snd_game_over = _load(self._assets_dir / self._config.game_over_sound) if self._config.game_over_sound else None

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def bind(self, subject: Subject) -> None:
        """Subscribe to all relevant game events. No-op when disabled."""
        if not self._config.enabled:
            return
        self._subscriptions = [
            subject.subscribe(GameStarted, self._on_game_started),
            subject.subscribe(MoveAccepted, self._on_move_accepted),
            subject.subscribe(PieceCaptured, self._on_piece_captured),
            subject.subscribe(GameOver, self._on_game_over),
        ]

    def unbind(self, subject: Subject) -> None:
        for sub in self._subscriptions:
            subject.unsubscribe(sub)
        self._subscriptions.clear()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_game_started(self, _event: GameStarted) -> None:
        _play(self._snd_game_start)

    def _on_move_accepted(self, _event: MoveAccepted) -> None:
        _play(self._snd_move)

    def _on_piece_captured(self, _event: PieceCaptured) -> None:
        _play(self._snd_capture)

    def _on_game_over(self, _event: GameOver) -> None:
        _play(self._snd_game_over)
