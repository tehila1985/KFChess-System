from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from engine.config import DEFAULT_CONFIG
from engine.game_engine import GameSnapshot
from ui.config.app_config import DEFAULT_APP_CONFIG
from ui.animation import interpolate_pixel
from ui.rendering.interfaces import IRenderer, RenderContext
from ui.vendor.img import Img


class TextRenderer:
    """
    Converts a GameSnapshot to printable text.

    Fully decoupled from the model, so it can be swapped with any other
    presentation layer without changing GameEngine.
    """

    def render(self, snapshot: GameSnapshot) -> str:
        """Full render: board + scores + game state."""
        scores = dict(snapshot.scores)
        lines = [" ".join(row) for row in snapshot.grid]
        lines.append(f"Score  w:{scores.get('w', 0)}  b:{scores.get('b', 0)}")
        if snapshot.game_over:
            lines.append(f"GAME OVER - winner: {snapshot.winner}")
        else:
            lines.append("Game in progress")
        return "\n".join(lines)

    def render_board_only(self, snapshot: GameSnapshot) -> str:
        """Renders board-only output used by CLI tests."""
        return "\n".join(" ".join(row) for row in snapshot.grid)


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
    hud_layout: object = DEFAULT_APP_CONFIG.hud_layout
    palette: object = DEFAULT_APP_CONFIG.palette
    font: object = DEFAULT_APP_CONFIG.font

    def _draw_side_panel(
        self,
        composed: Img,
        x: int,
        label: str,
        captures: int,
        entries: list[str],
    ) -> None:
        """Render one sidebar panel (white or black) at the given x offset."""
        lo = self.hud_layout
        cfg = self.hud_config
        pal = self.palette
        fnt = self.font

        composed.put_text(label, x, lo.label_y,
                          color_bgr=pal.text_primary_bgr, scale=1.0,
                          font=fnt.face, thickness=fnt.thickness)
        composed.put_text(f"{cfg.score_label}: {captures}", x, lo.score_y,
                          color_bgr=pal.text_secondary_bgr, scale=0.8,
                          font=fnt.face, thickness=fnt.thickness)
        composed.put_text(cfg.separator, x, lo.separator_y,
                          color_bgr=pal.text_muted_bgr, scale=0.5,
                          font=fnt.face, thickness=fnt.thickness)
        composed.put_text(cfg.moves_label, x, lo.moves_header_y,
                          color_bgr=pal.text_secondary_bgr, scale=0.65,
                          font=fnt.face, thickness=fnt.thickness)
        recent = entries[-lo.max_move_entries:]
        y = lo.entries_start_y
        for entry in reversed(recent):
            composed.put_text(entry, x, y,
                              color_bgr=pal.text_secondary_bgr, scale=0.53,
                              font=fnt.face, thickness=fnt.thickness)
            y += lo.entry_line_height

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

        lo = self.hud_layout
        pal = self.palette
        fnt = self.font

        # Left sidebar (white)
        self._draw_side_panel(
            composed,
            x=lo.panel_x_margin,
            label=self.hud_config.white_label,
            captures=self.scores.white_captures,
            entries=self.moves.white_entries,
        )

        # Right sidebar (black)
        right_x = self.sidebar_w + board_w + lo.right_panel_x_offset
        self._draw_side_panel(
            composed,
            x=right_x,
            label=self.hud_config.black_label,
            captures=self.scores.black_captures,
            entries=self.moves.black_entries,
        )

        # Banner — white text on a dark filled box for maximum contrast
        if self.banner.message:
            bx = self.sidebar_w + lo.banner_x_margin
            by = 40
            (text_w, text_h), baseline = cv2.getTextSize(
                self.banner.message,
                fnt.face,
                0.85,
                fnt.thickness,
            )
            box_pad = 6
            composed.fill_rect(
                bx - box_pad,
                by - text_h - box_pad,
                text_w + box_pad * 2,
                text_h + baseline + box_pad * 2,
                pal.banner_box_bgr,
            )
            composed.put_text(
                self.banner.message,
                bx,
                by,
                color_bgr=pal.banner_text_bgr,
                scale=0.85,
                font=fnt.face,
                thickness=fnt.thickness,
            )

        # Status line
        if ctx.status_line:
            composed.put_text(
                ctx.status_line,
                self.sidebar_w + lo.banner_x_margin,
                board_h - lo.status_y_from_bottom,
                color_bgr=pal.status_ok_bgr,
                scale=0.6,
                font=fnt.face,
                thickness=fnt.thickness,
            )

        return composed


@dataclass
class CompositeRenderer(IRenderer):
    renderers: tuple[IRenderer, ...]

    def draw(self, scene: Img, ctx: RenderContext) -> Img:
        current = scene
        for renderer in self.renderers:
            current = renderer.draw(current, ctx)
        return current
