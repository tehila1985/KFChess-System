from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UiAssetsConfig:
    board_size_px: int = 800
    piece_size_px: int = 84
    piece_padding_px: int = 8
    legal_marker_center_px: int = 42
    legal_marker_fill_radius_px: int = 12
    legal_marker_stroke_radius_px: int = 14
    legal_marker_stroke_width_px: int = 2


@dataclass(frozen=True)
class UiLayoutConfig:
    sidebar_background_rgb: tuple[int, int, int] = (50, 50, 50)


@dataclass(frozen=True)
class UiStatusTextConfig:
    idle_prompt: str = "Click a piece, then click destination. Press Q to quit."
    accepted: str = "Move accepted"
    cooldown: str = "Piece is cooling down - wait a moment."
    jump_requested: str = "Jump requested"
    fallback_prefix: str = "Move result"


@dataclass(frozen=True)
class UiRuntimeConfig:
    fallback_frame_ms: int = 16


@dataclass(frozen=True)
class AppConfig:
    assets: UiAssetsConfig = UiAssetsConfig()
    layout: UiLayoutConfig = UiLayoutConfig()
    status: UiStatusTextConfig = UiStatusTextConfig()
    runtime: UiRuntimeConfig = UiRuntimeConfig()


DEFAULT_APP_CONFIG = AppConfig()
