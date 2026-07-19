from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ui.config.app_config import AppConfig
from ui.config.ui_config import ASSETS_DIR, DEFAULT_UI_CONFIG
from ui.vendor.img import Img


ANIM_STATES = ("idle", "move", "jump", "short_rest", "long_rest")
PIECE_COLORS = ("w", "b")
PIECE_TYPES = ("K", "Q", "R", "B", "N", "P")


@dataclass(frozen=True)
class LoadedUiAssets:
    board_img: Img
    panel_bg: Img
    selection_overlay: Img
    legal_moves_overlay: Img
    cooldown_overlay: Img
    frames_by_token: dict[str, dict[str, list[Img]]]
    fps_by_token: dict[str, dict[str, int]]


def load_ui_assets(app_config: AppConfig) -> LoadedUiAssets:
    board_img = _load_board_image(app_config)
    panel_bg = _build_panel_background(app_config)
    selection_overlay = _build_selection_overlay(app_config)
    legal_moves_overlay = _build_legal_moves_overlay(app_config)
    cooldown_overlay = _load_cooldown_overlay(app_config)
    frames_by_token, fps_by_token = _load_piece_frames(app_config)

    return LoadedUiAssets(
        board_img=board_img,
        panel_bg=panel_bg,
        selection_overlay=selection_overlay,
        legal_moves_overlay=legal_moves_overlay,
        cooldown_overlay=cooldown_overlay,
        frames_by_token=frames_by_token,
        fps_by_token=fps_by_token,
    )


def _load_board_image(app_config: AppConfig) -> Img:
    board_size = app_config.assets.board_size_px
    board_img = Img.read(str(ASSETS_DIR / "board.png"))
    resized = cv2.resize(board_img.pixels, (board_size, board_size), interpolation=cv2.INTER_AREA)
    return Img(resized)


def _build_panel_background(app_config: AppConfig) -> Img:
    board_size = app_config.assets.board_size_px
    sidebar_width = DEFAULT_UI_CONFIG.sidebar_width_px
    background = app_config.layout.sidebar_background_rgb
    panel = np.full((board_size, sidebar_width, 3), background, dtype=np.uint8)
    return Img(panel)


def _build_selection_overlay(app_config: AppConfig) -> Img:
    piece_size = app_config.assets.piece_size_px
    edge = 4
    selection_px = np.zeros((piece_size, piece_size, 4), dtype=np.uint8)
    selection_px[:edge, :, :] = (0, 255, 255, 255)
    selection_px[-edge:, :, :] = (0, 255, 255, 255)
    selection_px[:, :edge, :] = (0, 255, 255, 255)
    selection_px[:, -edge:, :] = (0, 255, 255, 255)
    return Img(selection_px)


def _build_legal_moves_overlay(app_config: AppConfig) -> Img:
    piece_size = app_config.assets.piece_size_px
    center = app_config.assets.legal_marker_center_px
    fill_r = app_config.assets.legal_marker_fill_radius_px
    stroke_r = app_config.assets.legal_marker_stroke_radius_px
    stroke_w = app_config.assets.legal_marker_stroke_width_px

    legal_px = np.zeros((piece_size, piece_size, 4), dtype=np.uint8)
    cv2.circle(legal_px, (center, center), fill_r, (40, 220, 60, 210), -1)
    cv2.circle(legal_px, (center, center), stroke_r, (10, 110, 30, 220), stroke_w)
    return Img(legal_px)


def _load_cooldown_overlay(app_config: AppConfig) -> Img:
    piece_size = app_config.assets.piece_size_px
    cooldown_img = Img.read(str(ASSETS_DIR / "cooldown_fade" / "2.png"))
    resized = cv2.resize(cooldown_img.pixels, (piece_size, piece_size), interpolation=cv2.INTER_AREA)
    return Img(resized)


def _load_piece_frames(app_config: AppConfig) -> tuple[dict[str, dict[str, list[Img]]], dict[str, dict[str, int]]]:
    piece_root = ASSETS_DIR / DEFAULT_UI_CONFIG.skin_name / DEFAULT_UI_CONFIG.skin_name
    piece_size = app_config.assets.piece_size_px

    frames_by_token: dict[str, dict[str, list[Img]]] = {}
    fps_by_token: dict[str, dict[str, int]] = {}

    for color in PIECE_COLORS:
        for piece in PIECE_TYPES:
            token = f"{color}{piece}"
            code = f"{piece}{color.upper()}"
            token_states: dict[str, list[Img]] = {}
            token_fps: dict[str, int] = {}

            for state in ANIM_STATES:
                state_dir = piece_root / code / "states" / state
                sprites_dir = state_dir / "sprites"
                if not sprites_dir.exists():
                    continue

                frame_imgs: list[Img] = []
                for sprite_path in sorted(sprites_dir.glob("*.png"), key=lambda p: int(p.stem)):
                    sprite = Img.read(str(sprite_path))
                    resized = cv2.resize(sprite.pixels, (piece_size, piece_size), interpolation=cv2.INTER_AREA)
                    frame_imgs.append(Img(resized))
                if not frame_imgs:
                    continue

                fps = _read_fps(state_dir)
                token_states[state] = frame_imgs
                token_fps[state] = max(1, fps)

            if token_states:
                frames_by_token[token] = token_states
                fps_by_token[token] = token_fps

    return frames_by_token, fps_by_token


def _read_fps(state_dir: Path) -> int:
    default_fps = 6
    cfg = state_dir / "config.json"
    if not cfg.exists():
        return default_fps
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return default_fps
    return int(data.get("graphics", {}).get("frames_per_sec", default_fps))
