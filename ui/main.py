from __future__ import annotations

import cv2
from pathlib import Path

from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.game_engine import GameEngine
from engine.models.board import Board
from engine.rules.rule_engine import RuleEngine
from ui.board_mapper import BoardMapper
from ui.controller import Controller
from ui.state.game_events import MoveAccepted, MoveRejected
from ui.state.game_facade import GameFacade
from ui.ui_config import ASSETS_DIR, DEFAULT_UI_CONFIG
from ui.ui_components.banner import Banner
from ui.ui_components.moves_feed import MovesFeed
from ui.ui_components.score_panel import ScorePanel
from ui.vendor.img import Img


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


def _render_frame(
    board_img: Img,
    piece_cache: dict[str, Img],
    facade: GameFacade,
    mapper: BoardMapper,
    moves: MovesFeed,
    scores: ScorePanel,
    banner: Banner,
    status_line: str,
) -> Img:
    frame = board_img.copy()
    snapshot = facade.get_snapshot()

    cell_px = DEFAULT_UI_CONFIG.board_cell_px
    for row_idx, row in enumerate(snapshot.grid):
        for col_idx, token in enumerate(row):
            if token == ".":
                continue
            sprite = piece_cache.get(token)
            if sprite is None:
                continue
            x = col_idx * cell_px + 8
            y = row_idx * cell_px + 8
            sprite.draw_on(frame, x, y)

    frame.put_text(f"White captures: {scores.white_captures}", 10, 900, scale=0.7)
    frame.put_text(f"Black captures: {scores.black_captures}", 10, 925, scale=0.7)
    if moves.entries:
        frame.put_text(f"Last move: {moves.entries[-1]}", 420, 900, scale=0.6)
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

    piece_dir = ASSETS_DIR / "pieces3_source"
    piece_cache: dict[str, Img] = {}
    for color in ("w", "b"):
        for piece in ("K", "Q", "R", "B", "N", "P"):
            token = f"{color}{piece}"
            src = piece_dir / _token_to_source_file(token)
            if src.exists():
                sprite = Img.read(str(src))
                resized = cv2.resize(sprite.pixels, (84, 84), interpolation=cv2.INTER_AREA)
                piece_cache[token] = Img(resized)

    click_state = {"x": None, "y": None, "clicked": False}
    status_line = "Click a piece, then click destination. Press Q to quit."

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

        facade.tick(16)

        frame = _render_frame(
            board_img=board_img,
            piece_cache=piece_cache,
            facade=facade,
            mapper=mapper,
            moves=moves,
            scores=scores,
            banner=banner,
            status_line=status_line,
        )
        key = frame.show(window_title)
        if key in (ord("q"), ord("Q"), 27):
            break
        if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1:
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_game()
