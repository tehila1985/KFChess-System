from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UiAssetsConfig:
    board_size_px: int = 800
    piece_size_px: int = 84
    piece_padding_px: int = 8
    selection_border_px: int = 4
    legal_marker_center_px: int = 42
    legal_marker_fill_radius_px: int = 12
    legal_marker_stroke_radius_px: int = 14
    legal_marker_stroke_width_px: int = 2
    cooldown_overlay_frame_name: str = "2.png"


@dataclass(frozen=True)
class UiPieceCatalogConfig:
    colors: tuple[str, ...] = ("w", "b")
    types: tuple[str, ...] = ("K", "Q", "R", "B", "N", "P")
    animation_states: tuple[str, ...] = ("idle", "move", "jump", "short_rest", "long_rest")
    default_state: str = "idle"
    move_state: str = "move"
    jump_state: str = "jump"
    cooldown_state: str = "short_rest"
    rest_state: str = "long_rest"
    default_fps: int = 6


@dataclass(frozen=True)
class UiHudTextConfig:
    white_label: str = "White"
    black_label: str = "Black"
    score_label: str = "Score"
    moves_label: str = "Moves"
    separator: str = "----------------"


@dataclass(frozen=True)
class UiInputConfig:
    left_action: str = "move"
    right_action: str = "jump"


@dataclass(frozen=True)
class UiBoardConfig:
    default_lines: tuple[str, ...] = (
        "bR bN bB bQ bK bB bN bR",
        "bP bP bP bP bP bP bP bP",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        "wP wP wP wP wP wP wP wP",
        "wR wN wB wQ wK wB wN wR",
    )


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
    pieces: UiPieceCatalogConfig = UiPieceCatalogConfig()
    hud: UiHudTextConfig = UiHudTextConfig()
    input: UiInputConfig = UiInputConfig()
    board: UiBoardConfig = UiBoardConfig()
    layout: UiLayoutConfig = UiLayoutConfig()
    status: UiStatusTextConfig = UiStatusTextConfig()
    runtime: UiRuntimeConfig = UiRuntimeConfig()


DEFAULT_APP_CONFIG = AppConfig()
