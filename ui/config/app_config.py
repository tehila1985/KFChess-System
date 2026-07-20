from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2


@dataclass(frozen=True)
class UiAssetsConfig:
    assets_dir: Path = Path(__file__).resolve().parent.parent / "assets"
    board_size_px: int = 800
    piece_size_px: int = 84
    piece_padding_px: int = 8
    legal_marker_center_px: int = 42
    cooldown_overlay_frame_name: str = "2.png"


@dataclass(frozen=True)
class UiOverlayStyleConfig:
    selection_border_px: int = 4
    # All RGBA values follow OpenCV BGRA channel order
    selection_border_bgra: tuple[int, int, int, int] = (0, 255, 255, 255)
    legal_marker_fill_bgra: tuple[int, int, int, int] = (40, 220, 60, 210)
    legal_marker_fill_radius_px: int = 12
    legal_marker_stroke_bgra: tuple[int, int, int, int] = (10, 110, 30, 220)
    legal_marker_stroke_radius_px: int = 14
    legal_marker_stroke_width_px: int = 2


@dataclass(frozen=True)
class UiPanelStyleConfig:
    sidebar_width_px: int = 280
    # BGR channel order (OpenCV convention)
    background_bgr: tuple[int, int, int] = (50, 50, 50)


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
class UiHudLayoutConfig:
    """Pixel positions for all HUD text elements.

    All y-values are absolute pixel positions in the final composed frame.
    right_panel_x_offset is the gap in pixels between the right edge of the
    board and the start of the right sidebar text.
    """
    panel_x_margin: int = 24
    label_y: int = 56
    score_y: int = 90
    separator_y: int = 122
    moves_header_y: int = 150
    entries_start_y: int = 176
    entry_line_height: int = 22
    right_panel_x_offset: int = 16
    banner_x_margin: int = 12
    status_y_from_bottom: int = 16
    max_move_entries: int = 12


# All color values use OpenCV BGR(A) channel order.
@dataclass(frozen=True)
class UiColorPaletteConfig:
    # Text hierarchy
    text_primary_bgr: tuple[int, int, int] = (255, 255, 255)    # white
    text_secondary_bgr: tuple[int, int, int] = (235, 235, 235)  # near-white
    text_muted_bgr: tuple[int, int, int] = (190, 190, 190)      # grey
    # Status / feedback
    status_ok_bgr: tuple[int, int, int] = (30, 220, 30)         # green
    # Banner: white text on a dark box for maximum contrast
    banner_text_bgr: tuple[int, int, int] = (255, 255, 255)
    banner_box_bgr: tuple[int, int, int] = (20, 20, 20)


@dataclass(frozen=True)
class UiFontConfig:
    """OpenCV font settings used throughout the HUD."""
    face: int = cv2.FONT_HERSHEY_SIMPLEX
    thickness: int = 2


@dataclass(frozen=True)
class UiInputConfig:
    left_action: str = "move"
    right_action: str = "jump"


@dataclass(frozen=True)
class UiBoardConfig:
    cell_size_px: int = 100
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
    overlay: UiOverlayStyleConfig = UiOverlayStyleConfig()
    panel: UiPanelStyleConfig = UiPanelStyleConfig()


@dataclass(frozen=True)
class UiStatusTextConfig:
    idle_prompt: str = "Click a piece, then click destination. Press Q to quit."
    accepted: str = "Move accepted"
    cooldown: str = "Piece is cooling down - wait a moment."
    jump_requested: str = "Jump requested"
    fallback_prefix: str = "Move result"


@dataclass(frozen=True)
class UiRuntimeConfig:
    window_title: str = "Kung-Fu Chess"
    fallback_frame_ms: int = 16


@dataclass(frozen=True)
class UiThemeConfig:
    skin_name: str = "pieces4"


@dataclass(frozen=True)
class AppConfig:
    assets: UiAssetsConfig = UiAssetsConfig()
    pieces: UiPieceCatalogConfig = UiPieceCatalogConfig()
    hud: UiHudTextConfig = UiHudTextConfig()
    hud_layout: UiHudLayoutConfig = UiHudLayoutConfig()
    palette: UiColorPaletteConfig = UiColorPaletteConfig()
    font: UiFontConfig = UiFontConfig()
    input: UiInputConfig = UiInputConfig()
    board: UiBoardConfig = UiBoardConfig()
    layout: UiLayoutConfig = UiLayoutConfig()
    status: UiStatusTextConfig = UiStatusTextConfig()
    runtime: UiRuntimeConfig = UiRuntimeConfig()
    theme: UiThemeConfig = UiThemeConfig()

    def __post_init__(self) -> None:
        # board_size_px must be exactly 8 × cell_size_px so that BoardMapper
        # and BoardRenderer agree on where each cell sits.
        expected_cell = self.assets.board_size_px // 8
        assert self.board.cell_size_px == expected_cell, (
            f"cell_size_px ({self.board.cell_size_px}) must equal "
            f"board_size_px // 8 ({expected_cell}).  "
            f"Update one of board.cell_size_px or assets.board_size_px."
        )
        # Piece sprite + padding on each side must fill a full cell exactly.
        assert self.assets.piece_padding_px * 2 + self.assets.piece_size_px == self.board.cell_size_px, (
            f"piece_padding_px ({self.assets.piece_padding_px}) * 2 + "
            f"piece_size_px ({self.assets.piece_size_px}) must equal "
            f"cell_size_px ({self.board.cell_size_px})."
        )


DEFAULT_APP_CONFIG = AppConfig()
