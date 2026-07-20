from __future__ import annotations

import ctypes
import sys
import time

import cv2

from ui.animation import AnimationClock
from ui.composition.container import build_container
from ui.config.app_config import DEFAULT_APP_CONFIG
from ui.interaction.controller import ControllerOutcomeAdapter
from ui.rendering import BoardRenderer, CompositeRenderer, HudRenderer, RenderContext
from ui.resources.asset_loader import load_ui_assets
from ui.state.game_events import MoveAccepted, MoveRejected


LEFT_ACTION = DEFAULT_APP_CONFIG.input.left_action
RIGHT_ACTION = DEFAULT_APP_CONFIG.input.right_action

# Target frame duration.  60 fps ≈ 16.67 ms per frame.
_TARGET_FPS = 60
_FRAME_DURATION_S = 1.0 / _TARGET_FPS


def _raise_timer_resolution() -> bool:
    """On Windows, lower the system timer period to 1 ms.

    This prevents cv2.waitKey(1) from blocking for 15-20 ms (the default
    Windows timer resolution), which would cap the frame rate at ~50-60 fps
    with visible stutter. Returns True if the call succeeded.
    """
    if sys.platform != "win32":
        return False
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
        return True
    except Exception:
        return False


def _restore_timer_resolution() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass


def _process_pointer_action(
    *,
    action: str,
    x: int,
    y: int,
    sidebar_width: int,
    mapper,
    facade,
    ui_controller,
    current_status: str,
) -> str:
    """Routes pointer action to move or jump flow and returns next status line."""
    board_x = x - sidebar_width

    if action == RIGHT_ACTION:
        pos = mapper.to_position(board_x, y)
        if pos is None:
            return current_status
        facade.request_jump(pos)
        return DEFAULT_APP_CONFIG.status.jump_requested

    result = ui_controller.on_click(board_x, y)
    if result is None:
        return current_status
    if result.success:
        return DEFAULT_APP_CONFIG.status.accepted
    if result.reason is not None and result.reason.name == "PIECE_ON_COOLDOWN":
        return DEFAULT_APP_CONFIG.status.cooldown
    reason = result.reason.name if result.reason is not None else "UNKNOWN"
    return f"{DEFAULT_APP_CONFIG.status.fallback_prefix}: {reason}"


def run_game(board_lines: list[str] | None = None) -> None:
    lines = board_lines or list(DEFAULT_APP_CONFIG.board.default_lines)
    container = build_container(lines)
    facade = container.facade
    ui_controller = ControllerOutcomeAdapter(container.controller)

    assets = load_ui_assets(DEFAULT_APP_CONFIG)

    status_line = DEFAULT_APP_CONFIG.status.idle_prompt

    click_state: dict[str, object] = {
        "x": None,
        "y": None,
        "clicked": False,
        "action": LEFT_ACTION,
    }

    clock = AnimationClock()
    elapsed_ms = 0

    def _on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            click_state["x"] = x
            click_state["y"] = y
            click_state["action"] = LEFT_ACTION
            click_state["clicked"] = True
        elif event == cv2.EVENT_RBUTTONDOWN:
            click_state["x"] = x
            click_state["y"] = y
            click_state["action"] = RIGHT_ACTION
            click_state["clicked"] = True

    window_title = DEFAULT_APP_CONFIG.runtime.window_title
    cv2.namedWindow(window_title)
    cv2.setMouseCallback(window_title, _on_mouse)

    facade.subject.subscribe(MoveAccepted, lambda _event: None)
    facade.subject.subscribe(MoveRejected, lambda _event: None)

    renderer = CompositeRenderer(
        (
            BoardRenderer(
                board_img=assets.board_img,
                frames_by_token=assets.frames_by_token,
                fps_by_token=assets.fps_by_token,
                cooldown_overlay=assets.cooldown_overlay,
                facade=facade,
                selection_overlay=assets.selection_overlay,
                legal_moves_overlay=assets.legal_moves_overlay,
            ),
            HudRenderer(
                panel_bg=assets.panel_bg,
                sidebar_w=DEFAULT_APP_CONFIG.layout.panel.sidebar_width_px,
                moves=container.moves,
                scores=container.scores,
                banner=container.banner,
            ),
        )
    )

    _raise_timer_resolution()
    try:
        _run_loop(
            facade=facade,
            ui_controller=ui_controller,
            container=container,
            renderer=renderer,
            assets=assets,
            clock=clock,
            elapsed_ms=elapsed_ms,
            status_line=status_line,
            click_state=click_state,
            window_title=window_title,
        )
    finally:
        _restore_timer_resolution()
        cv2.destroyAllWindows()


def _run_loop(
    *,
    facade,
    ui_controller,
    container,
    renderer,
    assets,
    clock: AnimationClock,
    elapsed_ms: int,
    status_line: str,
    click_state: dict,
    window_title: str,
) -> None:
    frame_start = time.perf_counter()

    while True:
        # --- Input handling ------------------------------------------------
        if click_state["clicked"]:
            x = int(click_state["x"])           # type: ignore[arg-type]
            y = int(click_state["y"])           # type: ignore[arg-type]
            action = str(click_state["action"])
            click_state["clicked"] = False
            status_line = _process_pointer_action(
                action=action,
                x=x,
                y=y,
                sidebar_width=DEFAULT_APP_CONFIG.layout.panel.sidebar_width_px,
                mapper=container.mapper,
                facade=facade,
                ui_controller=ui_controller,
                current_status=status_line,
            )

        # --- Simulation tick -----------------------------------------------
        delta_ms = clock.tick_ms()
        if delta_ms <= 0:
            delta_ms = DEFAULT_APP_CONFIG.runtime.fallback_frame_ms
        elapsed_ms += delta_ms
        facade.tick(delta_ms)

        # --- Render --------------------------------------------------------
        pending = ui_controller.pending_src
        selected_pos = (
            (pending.row, pending.col) if pending is not None else None
        )
        ctx = RenderContext(
            elapsed_ms=elapsed_ms,
            status_line=status_line,
            selected_pos=selected_pos,
            legal_targets=tuple(
                (p.row, p.col) for p in facade.get_legal_destinations(pending)
            )
            if pending is not None
            else (),
        )

        frame = renderer.draw(assets.board_img.copy(), ctx)
        container.moves.dirty = False
        container.scores.dirty = False
        container.banner.dirty = False

        # --- Display & frame cap -------------------------------------------
        # cv2.waitKey(1) on Windows blocks for the OS timer period (~15 ms by
        # default). We call it with 1 ms so OpenCV pumps its event queue, then
        # busy-spin for the remainder of the frame budget using perf_counter.
        # Combined with timeBeginPeriod(1) this gives a stable ~60 fps.
        frame.show(window_title)
        key = cv2.waitKey(1)

        now = time.perf_counter()
        remaining = _FRAME_DURATION_S - (now - frame_start)
        if remaining > 0.002:
            # Sleep for most of the remaining time, then busy-spin the tail.
            time.sleep(remaining - 0.001)
        # Busy-spin for the final ~1 ms to hit the target precisely.
        while time.perf_counter() - frame_start < _FRAME_DURATION_S:
            pass
        frame_start = time.perf_counter()

        if key in (ord("q"), ord("Q"), 27):
            break
        if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1:
            break
