from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from engine.config import DEFAULT_CONFIG
from ui.config.app_config import DEFAULT_APP_CONFIG
from ui.animation import interpolate_pixel
from ui.rendering.interfaces import IRenderer, RenderContext
from ui.vendor.img import Img


@dataclass
class BoardRenderer(IRenderer):
    board_img: Img
    frames_by_token: dict[str, dict[str, list[Img]]]
    fps_by_token: dict[str, dict[str, int]]
    cooldown_overlay: Img
    facade: object
    selection_overlay: Img
    legal_moves_overlay: Img
    piece_config: object = DEFAULT_APP_CONFIG.pieces

    def _pick_piece_state(self, is_moving: bool, cooldown_end_ms: int | None, now_ms: int) -> str:
        if is_moving:
            return self.piece_config.move_state
        if cooldown_end_ms is not None and cooldown_end_ms > now_ms:
            return self.piece_config.cooldown_state
        return self.piece_config.default_state

    def _pick_frame(self, token: str, state: str, elapsed_ms: int) -> Img | None:
        token_states = self.frames_by_token.get(token)
        if not token_states:
            return None
        frames = token_states.get(state) or token_states.get(self.piece_config.default_state)
        if not frames:
            return None
        fps = self.fps_by_token.get(token, {}).get(
            state,
            self.fps_by_token.get(token, {}).get(self.piece_config.default_state, self.piece_config.default_fps),
        )
        idx = int((elapsed_ms / 1000.0) * max(1, fps)) % len(frames)
        return frames[idx]

    def draw(self, scene: Img, ctx: RenderContext) -> Img:
        _ = scene
        board_frame = self.board_img.copy()
        snapshot = self.facade.get_snapshot()
        active_motions = list(snapshot.active_motions)
        moving_sources = {motion.src for motion in active_motions}
        cooldown_until_by_pos: dict[tuple[int, int], int] = {
            (pos.row, pos.col): end_time for pos, end_time in snapshot.cooldowns
        }

        cell_px = DEFAULT_APP_CONFIG.assets.board_size_px // 8
        piece_padding = DEFAULT_APP_CONFIG.assets.piece_padding_px
        for row_idx, row in enumerate(snapshot.grid):
            for col_idx, token in enumerate(row):
                if token == ".":
                    continue
                if any(pos.row == row_idx and pos.col == col_idx for pos in moving_sources):
                    continue
                pos_key = (row_idx, col_idx)
                cooldown_end = cooldown_until_by_pos.get(pos_key)
                state = self._pick_piece_state(is_moving=False, cooldown_end_ms=cooldown_end, now_ms=ctx.elapsed_ms)
                sprite = self._pick_frame(token, state, ctx.elapsed_ms)
                if sprite is None:
                    continue
                x = col_idx * cell_px + piece_padding
                y = row_idx * cell_px + piece_padding
                sprite.draw_on(board_frame, x, y)

                if ctx.selected_pos == (row_idx, col_idx):
                    self.selection_overlay.draw_on(board_frame, x, y)

                if cooldown_end is not None and cooldown_end > ctx.elapsed_ms:
                    remaining = cooldown_end - ctx.elapsed_ms
                    total = max(1, DEFAULT_CONFIG.cooldown_ms)
                    progress = max(0.0, min(1.0, remaining / max(1, total)))
                    overlay_h = self.cooldown_overlay.pixels.shape[0]
                    clip_h = max(1, int(overlay_h * progress))
                    top_y = y + (overlay_h - clip_h)
                    overlay_part = Img(self.cooldown_overlay.pixels[overlay_h - clip_h :, :, :].copy())
                    overlay_part.draw_on(board_frame, x, top_y)

        for row_idx, col_idx in ctx.legal_targets:
            lx = col_idx * cell_px + piece_padding
            ly = row_idx * cell_px + piece_padding
            self.legal_moves_overlay.draw_on(board_frame, lx, ly)

        for motion in active_motions:
            motion_state = self.piece_config.jump_state if motion.is_jump else self.piece_config.move_state
            sprite = self._pick_frame(motion.piece.token, motion_state, ctx.elapsed_ms)
            if sprite is None:
                continue
            duration = max(1, motion.end_time - motion.start_time)
            elapsed = ctx.elapsed_ms - motion.start_time
            progress = max(0.0, min(1.0, elapsed / duration))
            src_px = (motion.src.col * cell_px + piece_padding, motion.src.row * cell_px + piece_padding)
            dst_px = (motion.dst.col * cell_px + piece_padding, motion.dst.row * cell_px + piece_padding)
            x, y = interpolate_pixel(src_px, dst_px, progress)
            sprite.draw_on(board_frame, x, y)

        if ctx.selected_pos is not None:
            sr, sc = ctx.selected_pos
            sx = sc * cell_px + piece_padding
            sy = sr * cell_px + piece_padding
            self.selection_overlay.draw_on(board_frame, sx, sy)

        return board_frame


@dataclass
class HudRenderer(IRenderer):
    panel_bg: Img
    sidebar_w: int
    moves: object
    scores: object
    banner: object
    hud_config: object = DEFAULT_APP_CONFIG.hud

    def draw(self, scene: Img, ctx: RenderContext) -> Img:
        board_h, board_w = scene.pixels.shape[:2]
        composed = Img(
            cv2.copyMakeBorder(
                scene.pixels,
                0,
                0,
                self.sidebar_w,
                self.sidebar_w,
                cv2.BORDER_CONSTANT,
                value=(0, 0, 0, 0) if scene.pixels.shape[2] == 4 else (0, 0, 0),
            )
        )
        self.panel_bg.draw_on(composed, 0, 0)
        self.panel_bg.draw_on(composed, self.sidebar_w + board_w, 0)
        scene.draw_on(composed, self.sidebar_w, 0)

        composed.put_text(self.hud_config.white_label, 24, 56, color=(255, 255, 255), scale=1.0)
        composed.put_text(f"{self.hud_config.score_label}: {self.scores.white_captures}", 24, 90, color=(235, 235, 235), scale=0.8)
        composed.put_text(self.hud_config.separator, 24, 122, color=(190, 190, 190), scale=0.5)
        composed.put_text(self.hud_config.moves_label, 24, 150, color=(235, 235, 235), scale=0.65)
        white_recent = self.moves.white_entries[-12:]
        left_y = 176
        for entry in reversed(white_recent):
            composed.put_text(entry, 24, left_y, color=(235, 235, 235), scale=0.53)
            left_y += 22

        right_x = self.sidebar_w + board_w + 16
        composed.put_text(self.hud_config.black_label, right_x, 56, color=(255, 255, 255), scale=1.0)
        composed.put_text(f"{self.hud_config.score_label}: {self.scores.black_captures}", right_x, 90, color=(235, 235, 235), scale=0.8)
        composed.put_text(self.hud_config.separator, right_x, 122, color=(190, 190, 190), scale=0.5)
        composed.put_text(self.hud_config.moves_label, right_x, 150, color=(235, 235, 235), scale=0.65)
        black_recent = self.moves.black_entries[-12:]
        right_y = 176
        for entry in reversed(black_recent):
            composed.put_text(entry, right_x, right_y, color=(235, 235, 235), scale=0.53)
            right_y += 22

        if self.banner.message:
            composed.put_text(self.banner.message, self.sidebar_w + 12, 40, color=(0, 0, 255), scale=0.85)
        if ctx.status_line:
            composed.put_text(ctx.status_line, self.sidebar_w + 12, board_h - 16, color=(30, 220, 30), scale=0.6)

        return composed


@dataclass
class CompositeRenderer(IRenderer):
    renderers: tuple[IRenderer, ...]

    def draw(self, scene: Img, ctx: RenderContext) -> Img:
        current = scene
        for renderer in self.renderers:
            current = renderer.draw(current, ctx)
        return current
