from __future__ import annotations

import cv2

from ui.animation import AnimationClock
from ui.composition.container import build_container
from ui.config.app_config import DEFAULT_APP_CONFIG
from ui.config.ui_config import DEFAULT_UI_CONFIG
from ui.interaction.controller_outcome import ControllerOutcomeAdapter
from ui.rendering import BoardRenderer, CompositeRenderer, DirtyState, HudRenderer, RenderContext
from ui.resources.asset_loader import load_ui_assets
from ui.state.game_events import MoveAccepted, MoveRejected


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
    input_config = DEFAULT_APP_CONFIG.input
    board_x = x - sidebar_width

    if action == input_config.right_action:
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
    controller = container.controller
    ui_controller = ControllerOutcomeAdapter(controller)

    assets = load_ui_assets(DEFAULT_APP_CONFIG)

    status_line = DEFAULT_APP_CONFIG.status.idle_prompt
    click_state = {"x": None, "y": None, "clicked": False, "action": LEFT_ACTION}

    clock = AnimationClock()
    elapsed_ms = 0
    ui_dirty = DirtyState(dirty=True)
    input_config = DEFAULT_APP_CONFIG.input

    def _on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            click_state["x"] = x
            click_state["y"] = y
            click_state["clicked"] = True
            click_state["action"] = input_config.left_action
        elif event == cv2.EVENT_RBUTTONDOWN:
            click_state["x"] = x
            click_state["y"] = y
            click_state["clicked"] = True
            click_state["action"] = input_config.right_action

    window_title = DEFAULT_UI_CONFIG.window_title
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
                sidebar_w=DEFAULT_UI_CONFIG.sidebar_width_px,
                moves=container.moves,
                scores=container.scores,
                banner=container.banner,
            ),
        )
    )

    while True:
        if click_state["clicked"]:
            x = int(click_state["x"])
            y = int(click_state["y"])
            action = str(click_state["action"])
            click_state["clicked"] = False
            status_line = _process_pointer_action(
                action=action,
                x=x,
                y=y,
                sidebar_width=DEFAULT_UI_CONFIG.sidebar_width_px,
                mapper=container.mapper,
                facade=facade,
                ui_controller=ui_controller,
                current_status=status_line,
            )
            ui_dirty.mark_dirty()

        delta_ms = clock.tick_ms()
        if delta_ms <= 0:
            delta_ms = DEFAULT_APP_CONFIG.runtime.fallback_frame_ms
        elapsed_ms += delta_ms
        facade.tick(delta_ms)

        if container.moves.dirty or container.scores.dirty or container.banner.dirty:
            ui_dirty.mark_dirty()

        selected_pos = (
            (controller.pending_src.row, controller.pending_src.col)
            if controller.pending_src is not None
            else None
        )
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

        frame = renderer.draw(assets.board_img.copy(), ctx)
        ui_dirty.clear()
        container.moves.dirty = False
        container.scores.dirty = False
        container.banner.dirty = False

        key = frame.show(window_title)
        if key in (ord("q"), ord("Q"), 27):
            break
        if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1:
            break

    cv2.destroyAllWindows()
