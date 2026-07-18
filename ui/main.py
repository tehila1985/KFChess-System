from __future__ import annotations

import cv2
import json
import numpy as np
from pathlib import Path

from engine.config import DEFAULT_CONFIG
from ui.board_mapper import BoardMapper
from ui.animation import AnimationClock, interpolate_pixel
from ui.container import build_container
from ui.controller_outcome import ControllerOutcomeAdapter
from ui.rendering import BoardRenderer, CompositeRenderer, DirtyState, HudRenderer, RenderContext
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


def run_game() -> None:
    board_lines = _default_board_lines()
    container = build_container(board_lines)
    facade = container.facade
    controller = container.controller
    ui_controller = ControllerOutcomeAdapter(controller)
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
    ui_dirty = DirtyState(dirty=True)

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

    renderer = CompositeRenderer(
        (
            BoardRenderer(
                board_img=board_img,
                frames_by_token=frames_by_token,
                fps_by_token=fps_by_token,
                cooldown_overlay=cooldown_overlay,
                facade=facade,
                selection_overlay=selection_overlay,
                legal_moves_overlay=legal_moves_overlay,
            ),
            HudRenderer(
                panel_bg=panel_bg,
                sidebar_w=sidebar_w,
                moves=moves,
                scores=scores,
                banner=banner,
            ),
        )
    )

    while True:
        if click_state["clicked"]:
            x = int(click_state["x"])
            y = int(click_state["y"])
            click_state["clicked"] = False
            # Board is centered between sidebars, so map window x to board-local x.
            result = ui_controller.on_click(x - sidebar_w, y)
            if result is not None:
                ui_dirty.mark_dirty()
                if result.success:
                    status_line = "Move accepted"
                elif result.reason is not None and result.reason.name == "PIECE_ON_COOLDOWN":
                    status_line = "Piece is cooling down - wait a moment."
                else:
                    reason = result.reason.name if result.reason is not None else "UNKNOWN"
                    status_line = f"Move result: {reason}"

        delta_ms = clock.tick_ms()
        if delta_ms <= 0:
            delta_ms = 16
        elapsed_ms += delta_ms
        facade.tick(delta_ms)

        if moves.dirty or scores.dirty or banner.dirty:
            ui_dirty.mark_dirty()

        selected_pos = (controller.pending_src.row, controller.pending_src.col) if controller.pending_src is not None else None
        if selected_pos is not None:
            ui_dirty.mark_dirty()
        ctx = RenderContext(
            elapsed_ms=elapsed_ms,
            status_line=status_line,
            selected_pos=selected_pos,
            legal_targets=tuple(
                (p.row, p.col) for p in facade.get_legal_destinations(controller.pending_src)
            )
            if controller.pending_src is not None
            else (),
        )
        frame = renderer.draw(board_img.copy(), ctx)
        ui_dirty.clear()
        moves.dirty = False
        scores.dirty = False
        banner.dirty = False
        key = frame.show(window_title)
        if key in (ord("q"), ord("Q"), 27):
            break
        if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1:
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_game()
