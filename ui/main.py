from __future__ import annotations

import cv2
import json
import numpy as np
from pathlib import Path

from engine.config import DEFAULT_CONFIG
from ui.board_mapper import BoardMapper
from ui.animation import AnimationClock, interpolate_pixel
from ui.container import build_container
from ui.state.game_events import MoveAccepted, MoveRejected
from ui.ui_config import ASSETS_DIR, DEFAULT_UI_CONFIG
from ui.vendor.img import Img


ANIM_STATES = ("idle", "move", "jump", "short_rest", "long_rest")


def _default_board_lines() -> list[str]:
    return [
        "bR bN bB bQ bK bB bN bR",
        "bP bP bP bP bP bP bP bP",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        "wP wP wP wP wP wP wP wP",
        "wR wN wB wQ wK wB wN wR",
    ]


def _token_to_source_file(token: str) -> str:
    color = token[0]
    piece = token[1]
    return f"{piece}{color.upper()}.png"


def _piece4_sprite_path(piece_root: Path, token: str) -> Path:
    # pieces4 structure: pieces4/<TOKEN>/states/idle/sprites/1.png
    return piece_root / f"{token[1]}{token[0].upper()}" / "states" / "idle" / "sprites" / "1.png"


def _load_piece4_frames(piece_root: Path) -> tuple[dict[str, dict[str, list[Img]]], dict[str, dict[str, int]]]:
    frames_by_token: dict[str, dict[str, list[Img]]] = {}
    fps_by_token: dict[str, dict[str, int]] = {}

    for color in ("w", "b"):
        for piece in ("K", "Q", "R", "B", "N", "P"):
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
                    resized = cv2.resize(sprite.pixels, (84, 84), interpolation=cv2.INTER_AREA)
                    frame_imgs.append(Img(resized))
                if not frame_imgs:
                    continue

                fps = 6
                cfg = state_dir / "config.json"
                if cfg.exists():
                    try:
                        data = json.loads(cfg.read_text(encoding="utf-8"))
                        fps = int(data.get("graphics", {}).get("frames_per_sec", fps))
                    except Exception:
                        fps = 6

                token_states[state] = frame_imgs
                token_fps[state] = max(1, fps)

            if token_states:
                frames_by_token[token] = token_states
                fps_by_token[token] = token_fps

    return frames_by_token, fps_by_token


def _pick_piece_state(
    is_moving: bool,
    cooldown_end_ms: int | None,
    now_ms: int,
) -> str:
    if is_moving:
        return "move"
    if cooldown_end_ms is not None and cooldown_end_ms > now_ms:
        return "short_rest"
    return "idle"


def _pick_frame(
    token: str,
    state: str,
    elapsed_ms: int,
    frames_by_token: dict[str, dict[str, list[Img]]],
    fps_by_token: dict[str, dict[str, int]],
) -> Img | None:
    token_states = frames_by_token.get(token)
    if not token_states:
        return None

    frames = token_states.get(state) or token_states.get("idle")
    if not frames:
        return None

    fps = fps_by_token.get(token, {}).get(state, fps_by_token.get(token, {}).get("idle", 6))
    idx = int((elapsed_ms / 1000.0) * max(1, fps)) % len(frames)
    return frames[idx]


def _render_frame(
    board_img: Img,
    panel_bg: Img,
    sidebar_w: int,
    frames_by_token: dict[str, dict[str, list[Img]]],
    fps_by_token: dict[str, dict[str, int]],
    cooldown_overlay: Img,
    facade: GameFacade,
    mapper: BoardMapper,
    moves: MovesFeed,
    scores: ScorePanel,
    banner: Banner,
    status_line: str,
    elapsed_ms: int,
    selected_pos: tuple[int, int] | None,
    selection_overlay: Img,
    legal_moves_overlay: Img,
    legal_targets: tuple[tuple[int, int], ...],
) -> Img:
    board_frame = board_img.copy()
    snapshot = facade.get_snapshot()
    active_motions = list(snapshot.active_motions)
    moving_sources = {motion.src for motion in active_motions}
    cooldown_until_by_pos: dict[tuple[int, int], int] = {
        (pos.row, pos.col): end_time for pos, end_time in snapshot.cooldowns
    }

    cell_px = DEFAULT_UI_CONFIG.board_cell_px
    for row_idx, row in enumerate(snapshot.grid):
        for col_idx, token in enumerate(row):
            if token == ".":
                continue
            if any(pos.row == row_idx and pos.col == col_idx for pos in moving_sources):
                continue
            pos_key = (row_idx, col_idx)
            cooldown_end = cooldown_until_by_pos.get(pos_key)
            state = _pick_piece_state(is_moving=False, cooldown_end_ms=cooldown_end, now_ms=elapsed_ms)
            sprite = _pick_frame(token, state, elapsed_ms, frames_by_token, fps_by_token)
            if sprite is None:
                continue
            x = col_idx * cell_px + 8
            y = row_idx * cell_px + 8
            sprite.draw_on(board_frame, x, y)

            if selected_pos == (row_idx, col_idx):
                selection_overlay.draw_on(board_frame, x, y)

            if cooldown_end is not None and cooldown_end > elapsed_ms:
                remaining = cooldown_end - elapsed_ms
                total = max(1, DEFAULT_CONFIG.cooldown_ms)
                # Remaining ratio drives a top-down fade-out mask.
                progress = max(0.0, min(1.0, remaining / max(1, total)))
                overlay_h = cooldown_overlay.pixels.shape[0]
                clip_h = max(1, int(overlay_h * progress))
                top_y = y + (overlay_h - clip_h)
                overlay_part = Img(cooldown_overlay.pixels[overlay_h - clip_h :, :, :].copy())
                overlay_part.draw_on(board_frame, x, top_y)

    for row_idx, col_idx in legal_targets:
        lx = col_idx * cell_px + 8
        ly = row_idx * cell_px + 8
        legal_moves_overlay.draw_on(board_frame, lx, ly)

    for motion in active_motions:
        motion_state = "jump" if motion.is_jump else "move"
        sprite = _pick_frame(motion.piece.token, motion_state, elapsed_ms, frames_by_token, fps_by_token)
        if sprite is None:
            continue

        duration = max(1, motion.end_time - motion.start_time)
        elapsed = elapsed_ms - motion.start_time
        progress = max(0.0, min(1.0, elapsed / duration))

        src_px = (motion.src.col * cell_px + 8, motion.src.row * cell_px + 8)
        dst_px = (motion.dst.col * cell_px + 8, motion.dst.row * cell_px + 8)
        x, y = interpolate_pixel(src_px, dst_px, progress)
        sprite.draw_on(board_frame, x, y)

    if selected_pos is not None:
        # If selected piece is in motion, draw selection at its source cell.
        sr, sc = selected_pos
        sx = sc * cell_px + 8
        sy = sr * cell_px + 8
        selection_overlay.draw_on(board_frame, sx, sy)

    board_h, board_w = board_frame.pixels.shape[:2]
    scene = Img(board_frame.pixels.copy())
    # Expand scene width to include sidebars.
    scene = Img(
        cv2.copyMakeBorder(
            board_frame.pixels,
            0,
            0,
            sidebar_w,
            sidebar_w,
            cv2.BORDER_CONSTANT,
            value=(0, 0, 0, 0) if board_frame.pixels.shape[2] == 4 else (0, 0, 0),
        )
    )
    panel_bg.draw_on(scene, 0, 0)
    panel_bg.draw_on(scene, sidebar_w + board_w, 0)
    board_frame.draw_on(scene, sidebar_w, 0)

    # Left panel: white summary
    scene.put_text("White", 24, 56, color=(255, 255, 255), scale=1.0)
    scene.put_text(f"Score: {scores.white_captures}", 24, 90, color=(235, 235, 235), scale=0.8)
    scene.put_text("----------------", 24, 122, color=(190, 190, 190), scale=0.5)
    scene.put_text("Moves", 24, 150, color=(235, 235, 235), scale=0.65)
    white_recent = moves.white_entries[-12:]
    left_y = 176
    for entry in reversed(white_recent):
        scene.put_text(entry, 24, left_y, color=(235, 235, 235), scale=0.53)
        left_y += 22

    # Right panel: black summary + moves feed from Observer subscribers
    right_x = sidebar_w + board_w + 16
    scene.put_text("Black", right_x, 56, color=(255, 255, 255), scale=1.0)
    scene.put_text(f"Score: {scores.black_captures}", right_x, 90, color=(235, 235, 235), scale=0.8)
    scene.put_text("----------------", right_x, 122, color=(190, 190, 190), scale=0.5)
    scene.put_text("Moves", right_x, 150, color=(235, 235, 235), scale=0.65)
    black_recent = moves.black_entries[-12:]
    right_y = 176
    for entry in reversed(black_recent):
        scene.put_text(entry, right_x, right_y, color=(235, 235, 235), scale=0.53)
        right_y += 22

    if banner.message:
        scene.put_text(banner.message, sidebar_w + 12, 40, color=(0, 0, 255), scale=0.85)
    if status_line:
        scene.put_text(status_line, sidebar_w + 12, board_h - 16, color=(30, 220, 30), scale=0.6)

    _ = mapper
    return scene


def run_game() -> None:
    board_lines = _default_board_lines()
    container = build_container(board_lines)
    facade = container.facade
    controller = container.controller
    moves = container.moves
    scores = container.scores
    banner = container.banner
    mapper = container.mapper

    board_img_path = ASSETS_DIR / "board.png"
    board_img = Img.read(str(board_img_path))
    board_img = Img(cv2.resize(board_img.pixels, (800, 800), interpolation=cv2.INTER_AREA))
    sidebar_w = 210

    panel_bg = Img(np.full((800, sidebar_w, 3), (50, 50, 50), dtype=np.uint8))

    selection_px = np.zeros((84, 84, 4), dtype=np.uint8)
    selection_px[:4, :, :] = (0, 255, 255, 255)
    selection_px[-4:, :, :] = (0, 255, 255, 255)
    selection_px[:, :4, :] = (0, 255, 255, 255)
    selection_px[:, -4:, :] = (0, 255, 255, 255)
    selection_overlay = Img(selection_px)

    legal_px = np.zeros((84, 84, 4), dtype=np.uint8)
    cv2.circle(legal_px, (42, 42), 12, (40, 220, 60, 210), -1)
    cv2.circle(legal_px, (42, 42), 14, (10, 110, 30, 220), 2)
    legal_moves_overlay = Img(legal_px)

    piece_dir = ASSETS_DIR / "pieces4" / "pieces4"
    frames_by_token, fps_by_token = _load_piece4_frames(piece_dir)

    cooldown_img_path = ASSETS_DIR / "cooldown_fade" / "2.png"
    cooldown_overlay = Img.read(str(cooldown_img_path))
    cooldown_overlay = Img(
        cv2.resize(cooldown_overlay.pixels, (84, 84), interpolation=cv2.INTER_AREA)
    )

    click_state = {"x": None, "y": None, "clicked": False}
    status_line = "Click a piece, then click destination. Press Q to quit."
    clock = AnimationClock()
    elapsed_ms = 0

    def _on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            click_state["x"] = x
            click_state["y"] = y
            click_state["clicked"] = True

    window_title = DEFAULT_UI_CONFIG.window_title
    cv2.namedWindow(window_title)
    cv2.setMouseCallback(window_title, _on_mouse)

    facade.subject.subscribe(MoveAccepted, lambda _event: None)
    facade.subject.subscribe(MoveRejected, lambda _event: None)

    while True:
        if click_state["clicked"]:
            x = int(click_state["x"])
            y = int(click_state["y"])
            click_state["clicked"] = False
            # Board is centered between sidebars, so map window x to board-local x.
            result = controller.on_click(x - sidebar_w, y)
            if result is not None:
                if result.name == "PIECE_ON_COOLDOWN":
                    status_line = "Piece is cooling down - wait a moment."
                else:
                    status_line = f"Move result: {result.name}"

        delta_ms = clock.tick_ms()
        if delta_ms <= 0:
            delta_ms = 16
        elapsed_ms += delta_ms
        facade.tick(delta_ms)

        frame = _render_frame(
            board_img=board_img,
            panel_bg=panel_bg,
            sidebar_w=sidebar_w,
            frames_by_token=frames_by_token,
            fps_by_token=fps_by_token,
            cooldown_overlay=cooldown_overlay,
            facade=facade,
            mapper=mapper,
            moves=moves,
            scores=scores,
            banner=banner,
            status_line=status_line,
            elapsed_ms=elapsed_ms,
            selected_pos=(controller.pending_src.row, controller.pending_src.col)
            if controller.pending_src is not None
            else None,
            selection_overlay=selection_overlay,
            legal_moves_overlay=legal_moves_overlay,
            legal_targets=tuple(
                (p.row, p.col) for p in facade.get_legal_destinations(controller.pending_src)
            )
            if controller.pending_src is not None
            else (),
        )
        key = frame.show(window_title)
        if key in (ord("q"), ord("Q"), 27):
            break
        if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1:
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_game()
