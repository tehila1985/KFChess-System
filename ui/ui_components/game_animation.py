from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from ui.config.app_config import DEFAULT_APP_CONFIG, UiAnimationConfig
from ui.state.game_events import GameOver, GameStarted, PieceCaptured
from ui.state.observer import Subject, Subscription
from ui.vendor.img import Img


@dataclass(frozen=True)
class CaptureFlash:
    """A short white flash centred on a captured cell."""
    row: int
    col: int
    remaining_ms: int


@dataclass
class AnimationState:
    """
    Current animation state exposed to renderers each frame.

    All fields are read-only from the renderer's perspective — only
    GameAnimationController mutates them via tick().
    """
    # 0.0 = fully black  →  1.0 = fully visible
    fade_alpha: float = 0.0
    # True while the start fade-in is running
    fading_in: bool = False
    # True while the game-over animation is running
    game_over_active: bool = False
    game_over_remaining_ms: int = 0
    # Active capture flashes (may be several simultaneously)
    capture_flashes: list[CaptureFlash] = field(default_factory=list)


@dataclass
class GameAnimationController:
    """
    Pub/sub subscriber that drives board-level overlay animations.

    Subscribes to:
      - GameStarted  → triggers the board fade-in
      - GameOver     → triggers the game-over hold state
      - PieceCaptured → triggers a short flash on the captured cell

    Call ``tick(delta_ms)`` once per frame from the game loop so that
    time-based animations advance correctly.

    The ``state`` property gives renderers a snapshot of current animation
    values to use when compositing their overlays.
    """

    _config: UiAnimationConfig = field(
        default_factory=lambda: DEFAULT_APP_CONFIG.animation
    )
    _state: AnimationState = field(default_factory=AnimationState, init=False)
    _subscriptions: list[Subscription] = field(default_factory=list, init=False)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> AnimationState:
        return self._state

    def bind(self, subject: Subject) -> None:
        self._subscriptions = [
            subject.subscribe(GameStarted, self._on_game_started),
            subject.subscribe(GameOver, self._on_game_over),
            subject.subscribe(PieceCaptured, self._on_piece_captured),
        ]

    def unbind(self, subject: Subject) -> None:
        for sub in self._subscriptions:
            subject.unsubscribe(sub)
        self._subscriptions.clear()

    def tick(self, delta_ms: int) -> None:
        """Advance all running animations by delta_ms milliseconds."""
        cfg = self._config
        st = self._state

        # --- Fade-in ---
        if st.fading_in:
            step = delta_ms / max(1, cfg.game_start_fade_in_ms)
            st.fade_alpha = min(1.0, st.fade_alpha + step)
            if st.fade_alpha >= 1.0:
                st.fading_in = False

        # --- Game-over hold ---
        if st.game_over_active:
            st.game_over_remaining_ms = max(0, st.game_over_remaining_ms - delta_ms)
            if st.game_over_remaining_ms == 0:
                st.game_over_active = False

        # --- Capture flashes ---
        still_active: list[CaptureFlash] = []
        for flash in st.capture_flashes:
            remaining = flash.remaining_ms - delta_ms
            if remaining > 0:
                still_active.append(CaptureFlash(flash.row, flash.col, remaining))
        st.capture_flashes = still_active

    def apply_to_board(self, board_img: Img) -> Img:
        """
        Composite all active animation overlays onto board_img in-place
        and return it.  Called by BoardRenderer after all pieces are drawn.
        """
        st = self._state
        cfg = self._config
        cell_px = DEFAULT_APP_CONFIG.assets.board_size_px // 8

        # --- Capture flashes ---
        for flash in st.capture_flashes:
            progress = flash.remaining_ms / max(1, cfg.capture_flash_ms)
            # Alpha fades out as the flash ages (bright at start, gone at end).
            alpha = int(cfg.capture_flash_bgra[3] * progress)
            if alpha <= 0:
                continue
            x = flash.col * cell_px
            y = flash.row * cell_px
            overlay = np.zeros((cell_px, cell_px, 4), dtype=np.uint8)
            overlay[:, :] = (*cfg.capture_flash_bgra[:3], alpha)
            Img(overlay).draw_on(board_img, x, y)

        # --- Fade-in (dim overlay that clears as alpha rises) ---
        if st.fading_in or st.fade_alpha < 1.0:
            dim_alpha = int(255 * (1.0 - st.fade_alpha))
            if dim_alpha > 0:
                h, w = board_img.pixels.shape[:2]
                dim = np.zeros((h, w, 4), dtype=np.uint8)
                dim[:, :, 3] = dim_alpha  # black with fading transparency
                Img(dim).draw_on(board_img, 0, 0)

        return board_img

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    def _on_game_started(self, _event: GameStarted) -> None:
        self._state.fade_alpha = 0.0
        self._state.fading_in = True

    def _on_game_over(self, _event: GameOver) -> None:
        self._state.game_over_active = True
        self._state.game_over_remaining_ms = self._config.game_over_hold_ms

    def _on_piece_captured(self, event: PieceCaptured) -> None:
        self._state.capture_flashes.append(
            CaptureFlash(
                row=event.at.row,
                col=event.at.col,
                remaining_ms=self._config.capture_flash_ms,
            )
        )
