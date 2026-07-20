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


# ---------------------------------------------------------------------------
# BoardRenderer
# ---------------------------------------------------------------------------

@dataclass
class BoardRenderer(IRenderer):
    board_img: Img
    frames_by_token: dict[str, dict[str, list[Img]]]
    fps_by_token: dict[str, dict[str, int]]
    cooldown_overlay: Img
    facade: object
    selection_overlay: Img
    legal_moves_overlay: Img
    anim: object = None                          # GameAnimationController | None
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
                    overlay_part = Img(self.cooldown_overlay.pixels[overlay_h - clip_h:, :, :].copy())
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

        # Apply animation overlays (capture flash, fade-in) on top of pieces.
        if self.anim is not None:
            self.anim.apply_to_board(board_frame)

        return board_frame


# ---------------------------------------------------------------------------
# HudRenderer — redesigned panel
# ---------------------------------------------------------------------------

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
    panel_style: object = DEFAULT_APP_CONFIG.layout.panel

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _draw_header_band(
        self,
        composed: Img,
        panel_x: int,
        label: str,
        header_color_bgr: tuple[int, int, int],
    ) -> None:
        """Filled colour band at the top of a sidebar with a large player label."""
        lo = self.hud_layout
        fnt = self.font
        pal = self.palette

        # Background fill for the header band
        composed.fill_rect(
            panel_x, 0,
            self.sidebar_w, lo.header_band_h,
            header_color_bgr,
        )

        # Player name — bold font, large, white
        composed.put_text(
            label,
            panel_x + lo.panel_x_margin,
            lo.label_y,
            color_bgr=pal.text_primary_bgr,
            scale=1.1,
            font=fnt.face_bold,
            thickness=fnt.thickness_bold,
        )

    def _draw_score_row(
        self,
        composed: Img,
        panel_x: int,
        captures: int,
        captured_symbols: str,
    ) -> None:
        """Score box with point total and captured piece symbols."""
        lo = self.hud_layout
        fnt = self.font
        pal = self.palette
        ps = self.panel_style
        cfg = self.hud_config

        # Score box background
        composed.fill_rect(
            panel_x + lo.panel_x_margin,
            lo.score_row_top,
            lo.panel_inner_width,
            lo.score_row_h,
            ps.score_box_bgr,
        )

        # "PTS" label in muted grey
        composed.put_text(
            cfg.score_label,
            panel_x + lo.panel_x_margin + 6,
            lo.score_value_y,
            color_bgr=pal.text_muted_bgr,
            scale=0.55,
            font=fnt.face,
            thickness=fnt.thickness,
        )

        # Point value — bright accent colour
        pts_text = str(captures)
        composed.put_text(
            pts_text,
            panel_x + lo.panel_x_margin + 48,
            lo.score_value_y,
            color_bgr=pal.score_text_bgr,
            scale=0.85,
            font=fnt.face_bold,
            thickness=fnt.thickness_bold,
        )

        # Captured piece symbols (e.g. "Q N P P") right-aligned stub
        if captured_symbols:
            composed.put_text(
                captured_symbols,
                panel_x + lo.panel_x_margin + 90,
                lo.score_value_y,
                color_bgr=pal.text_muted_bgr,
                scale=0.45,
                font=fnt.face,
                thickness=fnt.thickness,
            )

    def _draw_divider(self, composed: Img, panel_x: int) -> None:
        """Horizontal rule drawn directly on the pixel buffer."""
        lo = self.hud_layout
        ps = self.panel_style
        x0 = panel_x + lo.panel_x_margin
        x1 = panel_x + self.sidebar_w - lo.panel_x_margin
        y = lo.divider_y
        cv2.line(
            composed.pixels,
            (x0, y), (x1, y),
            ps.divider_bgr,
            lo.divider_thickness,
            cv2.LINE_AA,
        )

    def _draw_moves_section(
        self,
        composed: Img,
        panel_x: int,
        entries: list[str],
    ) -> None:
        """Moves header + numbered list of recent moves, newest at top."""
        lo = self.hud_layout
        fnt = self.font
        pal = self.palette
        cfg = self.hud_config
        ps = self.panel_style

        # Section header
        composed.put_text(
            cfg.moves_label,
            panel_x + lo.panel_x_margin,
            lo.moves_header_y,
            color_bgr=pal.text_muted_bgr,
            scale=0.5,
            font=fnt.face_bold,
            thickness=fnt.thickness,
        )

        # How many entries fit in the remaining panel height — constant once
        # the panel size is fixed, so the slice is always small.
        panel_h = composed.pixels.shape[0]
        available_h = panel_h - lo.entries_start_y - 10
        visible_count = max(1, available_h // lo.entry_line_height)
        recent = entries[-visible_count:]
        # Display number counts from the true total, but we only render
        # the visible window so len(entries) is not traversed each frame.
        total = len(entries)

        y = lo.entries_start_y
        for i, entry in enumerate(reversed(recent)):
            move_num = total - i
            row_bg = ps.move_alt_bg_bgr if (move_num % 2 == 0) else None

            # Alternating row background
            if row_bg is not None:
                composed.fill_rect(
                    panel_x + lo.panel_x_margin,
                    y - lo.entry_line_height + 4,
                    lo.panel_inner_width,
                    lo.entry_line_height,
                    row_bg,
                )

            # Move number
            composed.put_text(
                f"{move_num}.",
                panel_x + lo.panel_x_margin + 2,
                y,
                color_bgr=pal.text_number_bgr,
                scale=0.42,
                font=fnt.face,
                thickness=fnt.thickness,
            )

            # Move notation
            composed.put_text(
                entry,
                panel_x + lo.panel_x_margin + lo.entry_num_width,
                y,
                color_bgr=pal.text_secondary_bgr,
                scale=0.44,
                font=fnt.face,
                thickness=fnt.thickness,
            )

            y += lo.entry_line_height

    def _draw_side_panel(
        self,
        composed: Img,
        panel_x: int,
        label: str,
        captures: int,
        captured_symbols: str,
        entries: list[str],
        header_color_bgr: tuple[int, int, int],
    ) -> None:
        """Render a full sidebar panel at panel_x."""
        ps = self.panel_style

        # Panel background
        composed.fill_rect(panel_x, 0, self.sidebar_w, composed.pixels.shape[0], ps.background_bgr)

        self._draw_header_band(composed, panel_x, label, header_color_bgr)
        self._draw_score_row(composed, panel_x, captures, captured_symbols)
        self._draw_divider(composed, panel_x)
        self._draw_moves_section(composed, panel_x, entries)

    # ------------------------------------------------------------------
    # IRenderer.draw
    # ------------------------------------------------------------------

    def draw(self, scene: Img, ctx: RenderContext) -> Img:
        board_h, board_w = scene.pixels.shape[:2]
        pal = self.palette
        fnt = self.font
        lo = self.hud_layout

        composed = Img(
            cv2.copyMakeBorder(
                scene.pixels,
                0, 0,
                self.sidebar_w, self.sidebar_w,
                cv2.BORDER_CONSTANT,
                value=(0, 0, 0, 0) if scene.pixels.shape[2] == 4 else (0, 0, 0),
            )
        )

        # Place board in center
        scene.draw_on(composed, self.sidebar_w, 0)

        # Left panel — White
        self._draw_side_panel(
            composed,
            panel_x=0,
            label=self.hud_config.white_label,
            captures=self.scores.white_captures,
            captured_symbols=getattr(self.scores, "white_symbols", ""),
            entries=self.moves.white_entries,
            header_color_bgr=self.palette.white_player_header_bgr,
        )

        # Right panel — Black
        self._draw_side_panel(
            composed,
            panel_x=self.sidebar_w + board_w,
            label=self.hud_config.black_label,
            captures=self.scores.black_captures,
            captured_symbols=getattr(self.scores, "black_symbols", ""),
            entries=self.moves.black_entries,
            header_color_bgr=self.palette.black_player_header_bgr,
        )

        # Thin border lines between panels and board
        bx_left = self.sidebar_w
        bx_right = self.sidebar_w + board_w - 1
        cv2.line(composed.pixels, (bx_left, 0), (bx_left, board_h - 1),
                 self.panel_style.divider_bgr, 2)
        cv2.line(composed.pixels, (bx_right, 0), (bx_right, board_h - 1),
                 self.panel_style.divider_bgr, 2)

        # Banner — white text on a dark filled box, centred on board
        if self.banner.message:
            bx = self.sidebar_w + lo.banner_x_margin
            by = 48
            (text_w, text_h), baseline = cv2.getTextSize(
                self.banner.message, fnt.face_bold, 1.1, fnt.thickness_bold,
            )
            box_pad = 10
            # Semi-dark fill spanning full board width
            composed.fill_rect(
                self.sidebar_w,
                by - text_h - box_pad,
                board_w,
                text_h + baseline + box_pad * 2,
                pal.banner_box_bgr,
            )
            # Centred text
            text_x = self.sidebar_w + (board_w - text_w) // 2
            composed.put_text(
                self.banner.message,
                text_x, by,
                color_bgr=pal.banner_text_bgr,
                scale=1.1,
                font=fnt.face_bold,
                thickness=fnt.thickness_bold,
            )

        # Status line — bottom of board area
        if ctx.status_line:
            composed.fill_rect(
                self.sidebar_w,
                board_h - lo.status_y_from_bottom - 16,
                board_w,
                lo.status_y_from_bottom + 16,
                (0, 0, 0),
            )
            composed.put_text(
                ctx.status_line,
                self.sidebar_w + lo.banner_x_margin,
                board_h - 6,
                color_bgr=pal.status_ok_bgr,
                scale=0.52,
                font=fnt.face,
                thickness=fnt.thickness,
            )

        return composed


# ---------------------------------------------------------------------------
# CompositeRenderer
# ---------------------------------------------------------------------------

@dataclass
class CompositeRenderer(IRenderer):
    renderers: tuple[IRenderer, ...]

    def draw(self, scene: Img, ctx: RenderContext) -> Img:
        current = scene
        for renderer in self.renderers:
            current = renderer.draw(current, ctx)
        return current
