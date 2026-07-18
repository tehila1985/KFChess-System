from __future__ import annotations

import cv2
import json
from pathlib import Path

from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.game_engine import GameEngine
from engine.models.board import Board
from engine.rules.rule_engine import RuleEngine
from engine.config import DEFAULT_CONFIG
from ui.board_mapper import BoardMapper
from ui.controller import Controller
from ui.animation import AnimationClock, interpolate_pixel
from ui.state.game_events import MoveAccepted, MoveRejected
from ui.state.game_facade import GameFacade
from ui.ui_config import ASSETS_DIR, DEFAULT_UI_CONFIG
from ui.ui_components.banner import Banner
from ui.ui_components.moves_feed import MovesFeed
from ui.ui_components.score_panel import ScorePanel
from ui.vendor.img import Img


ANIM_STATES = ("idle", "move", "jump", "short_rest", "long_rest")


def build_ui(board_lines: list[str]) -> tuple[GameFacade, Controller, MovesFeed, ScorePanel, Banner]:
    board = Board(board_lines)
    engine = GameEngine(board, RuleEngine(), RealTimeArbiter(board))
    facade = GameFacade(engine)

    mapper = BoardMapper(
        cell_size=DEFAULT_UI_CONFIG.board_cell_px,
        rows=len(board_lines),
        cols=len(board_lines[0].split()),
    )
    controller = Controller(facade, mapper)

    moves = MovesFeed()
    scores = ScorePanel()
    banner = Banner()
    moves.bind(facade.subject)
    scores.bind(facade.subject)
    banner.bind(facade.subject)

    return facade, controller, moves, scores, banner


def _default_board_lines() -> list[str]:
    return [
        "bR bN bR bK bQ bR bN bR",
        "bP bP bP bP bP bP bP bP",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        ". . . . . . . .",
        "wP wP wP wP wP wP wP wP",
        "wR wN wR wK wQ wR wN wR",
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
) -> Img:
    frame = board_img.copy()
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
            sprite.draw_on(frame, x, y)

            if cooldown_end is not None and cooldown_end > elapsed_ms:
                remaining = cooldown_end - elapsed_ms
                total = max(1, DEFAULT_CONFIG.cooldown_ms)
                # Remaining ratio drives a top-down fade-out mask.
                progress = max(0.0, min(1.0, remaining / max(1, total)))
                overlay_h = cooldown_overlay.pixels.shape[0]
                clip_h = max(1, int(overlay_h * progress))
                top_y = y + (overlay_h - clip_h)
                overlay_part = Img(cooldown_overlay.pixels[overlay_h - clip_h :, :, :].copy())
                overlay_part.draw_on(frame, x, top_y)

    for motion in active_motions:
        sprite = _pick_frame(motion.piece.token, "move", elapsed_ms, frames_by_token, fps_by_token)
        if sprite is None:
            continue

        duration = max(1, motion.end_time - motion.start_time)
        elapsed = elapsed_ms - motion.start_time
        progress = max(0.0, min(1.0, elapsed / duration))

        src_px = (motion.src.col * cell_px + 8, motion.src.row * cell_px + 8)
        dst_px = (motion.dst.col * cell_px + 8, motion.dst.row * cell_px + 8)
        x, y = interpolate_pixel(src_px, dst_px, progress)
        sprite.draw_on(frame, x, y)

    frame.put_text(f"White captures: {scores.white_captures}", 10, 770, scale=0.7)
    frame.put_text(f"Black captures: {scores.black_captures}", 10, 792, scale=0.7)
    if moves.entries:
        frame.put_text(f"Last move: {moves.entries[-1]}", 350, 770, scale=0.6)
    if len(moves.entries) > 1:
        frame.put_text(f"Prev move: {moves.entries[-2]}", 350, 792, scale=0.55)
    if banner.message:
        frame.put_text(banner.message, 10, 45, color=(0, 0, 255), scale=1.0)
    if status_line:
        frame.put_text(status_line, 10, 70, color=(30, 180, 30), scale=0.7)

    _ = mapper
    return frame


def run_game() -> None:
    board_lines = _default_board_lines()
    facade, controller, moves, scores, banner = build_ui(board_lines)
    mapper = BoardMapper(
        cell_size=DEFAULT_UI_CONFIG.board_cell_px,
        rows=len(board_lines),
        cols=len(board_lines[0].split()),
    )

    board_img_path = ASSETS_DIR / "board.png"
    board_img = Img.read(str(board_img_path))
    board_img = Img(cv2.resize(board_img.pixels, (800, 800), interpolation=cv2.INTER_AREA))

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
            result = controller.on_click(x, y)
            if result is not None:
                status_line = f"Move result: {result.name}"

        delta_ms = clock.tick_ms()
        if delta_ms <= 0:
            delta_ms = 16
        elapsed_ms += delta_ms
        facade.tick(delta_ms)

        frame = _render_frame(
            board_img=board_img,
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
        )
        key = frame.show(window_title)
        if key in (ord("q"), ord("Q"), 27):
            break
        if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1:
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_game()
