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
    # All values follow OpenCV BGRA channel order
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
    background_bgr: tuple[int, int, int] = (32, 32, 38)       # deep dark blue-grey
    header_bg_bgr: tuple[int, int, int] = (45, 45, 55)        # slightly lighter header band
    score_box_bgr: tuple[int, int, int] = (55, 80, 40)        # dark green tint for score box
    divider_bgr: tuple[int, int, int] = (80, 80, 95)          # subtle divider line
    move_alt_bg_bgr: tuple[int, int, int] = (40, 40, 48)      # alternating row bg


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
    white_label: str = "WHITE"
    black_label: str = "BLACK"
    score_label: str = "PTS"
    moves_label: str = "MOVES"


@dataclass(frozen=True)
class UiHudLayoutConfig:
    """Pixel geometry for the HUD panels.

    All y-values are absolute pixel positions in the final composed frame.
    right_panel_x_offset: gap between right board edge and right sidebar text.
    """
    panel_x_margin: int = 16          # left text margin inside panel
    panel_inner_width: int = 248      # usable width inside panel (sidebar_width - 2*margin)

    # Header band
    header_band_h: int = 70           # height of the coloured header strip
    label_y: int = 44                 # baseline of the player name inside header

    # Score row  (below header)
    score_row_top: int = 78           # top of score box
    score_row_h: int = 36
    score_value_y: int = 102          # text baseline inside score box

    # Divider
    divider_y: int = 122
    divider_thickness: int = 1

    # Moves section
    moves_header_y: int = 146
    entries_start_y: int = 172
    entry_line_height: int = 20
    entry_num_width: int = 28         # width reserved for the move number

    right_panel_x_offset: int = 16   # gap from board right edge to panel text
    banner_x_margin: int = 12
    status_y_from_bottom: int = 20
    max_move_entries: int = 28        # max entries to keep in memory (shown: fits panel)


# All color values use OpenCV BGR(A) channel order.
@dataclass(frozen=True)
class UiColorPaletteConfig:
    # Text hierarchy
    text_primary_bgr: tuple[int, int, int] = (255, 255, 255)       # white
    text_secondary_bgr: tuple[int, int, int] = (210, 210, 220)     # light grey
    text_muted_bgr: tuple[int, int, int] = (140, 140, 155)         # dim grey
    text_accent_bgr: tuple[int, int, int] = (100, 210, 255)        # gold-ish (BGR: warm yellow)
    text_number_bgr: tuple[int, int, int] = (120, 160, 200)        # steel blue for move numbers

    # White player accent (header gradient approximation — solid colour)
    white_player_header_bgr: tuple[int, int, int] = (180, 160, 100)   # warm bronze/gold
    # Black player accent
    black_player_header_bgr: tuple[int, int, int] = (60, 60, 80)      # dark slate

    # Status / feedback
    status_ok_bgr: tuple[int, int, int] = (60, 200, 60)            # green
    status_warn_bgr: tuple[int, int, int] = (30, 160, 240)         # amber (BGR)

    # Banner
    banner_text_bgr: tuple[int, int, int] = (255, 255, 255)
    banner_box_bgr: tuple[int, int, int] = (20, 20, 20)

    # Score box
    score_text_bgr: tuple[int, int, int] = (80, 255, 140)          # bright green score value


@dataclass(frozen=True)
class UiFontConfig:
    """OpenCV font settings used throughout the HUD."""
    face: int = cv2.FONT_HERSHEY_SIMPLEX
    face_bold: int = cv2.FONT_HERSHEY_DUPLEX   # slightly heavier for titles
    thickness: int = 1
    thickness_bold: int = 2


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
    idle_prompt: str = "Click a piece, then a destination.  Q = quit"
    accepted: str = "Move accepted"
    cooldown: str = "Piece cooling down..."
    jump_requested: str = "Jump requested"
    fallback_prefix: str = "Rejected"


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
        expected_cell = self.assets.board_size_px // 8
        assert self.board.cell_size_px == expected_cell, (
            f"cell_size_px ({self.board.cell_size_px}) must equal "
            f"board_size_px // 8 ({expected_cell})."
        )
        assert self.assets.piece_padding_px * 2 + self.assets.piece_size_px == self.board.cell_size_px, (
            f"piece_padding_px ({self.assets.piece_padding_px}) * 2 + "
            f"piece_size_px ({self.assets.piece_size_px}) must equal "
            f"cell_size_px ({self.board.cell_size_px})."
        )


DEFAULT_APP_CONFIG = AppConfig()
