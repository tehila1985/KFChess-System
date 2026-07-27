"""
game_scene.py — the networked game board.

Reuses the existing local-game rendering/animation/sound stack unchanged:
ui.composition.container.build_container, ui.resources.asset_loader,
ui.rendering.renderers (BoardRenderer/HudRenderer/CompositeRenderer),
ui.interaction.controller.Controller/BoardMapper, ui.animation.AnimationClock.

Design (see plan): the local GameFacade/GameEngine mirror is never mutated
by a local click — only by replaying moves the SERVER has already
confirmed (MOVE_BROADCAST, which is sent to both players for every
accepted move, including your own). Clicking only sends a MOVE request;
NetworkMoveRequester is the _MoveRequester adapter that makes this work
without touching Controller itself.
"""
from __future__ import annotations

from dataclasses import replace

import cv2

from engine.models.position import Position
from ui.animation import AnimationClock
from ui.composition.container import build_container
from ui.config.app_config import DEFAULT_APP_CONFIG
from ui.interaction.controller import Controller, ControllerOutcomeAdapter
from ui.rendering import BoardRenderer, CompositeRenderer, HudRenderer, RenderContext
from ui.resources.asset_loader import load_ui_assets
from ui.state.outcome import ActionOutcome
from ui.vendor.img import Img

from client.gui.widgets import Button
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, MovePayload, ResignPayload

_SIDEBAR_W = DEFAULT_APP_CONFIG.layout.panel.sidebar_width_px
_BOARD_SIZE = DEFAULT_APP_CONFIG.assets.board_size_px
_FRAME_W = _SIDEBAR_W * 2 + _BOARD_SIZE
_FRAME_H = _BOARD_SIZE
_BAR_H = 56
CANVAS_W = _FRAME_W
CANVAS_H = _FRAME_H + _BAR_H


class _Reason:
    """Duck-typed stand-in for RequestMoveResult — only `.name` is read by status text."""

    def __init__(self, name: str) -> None:
        self.name = name


class NetworkMoveRequester:
    """
    _MoveRequester adapter passed to Controller.

    Reads (get_piece_at/is_on_cooldown/is_game_over) proxy to the local
    mirror facade so click feedback stays responsive. request_move does
    NOT mutate the mirror — it only sends MOVE to the server and returns
    the server's accept/reject outcome; the mirror is mutated later, when
    the resulting MOVE_BROADCAST is replayed (see GameScene.update).
    """

    def __init__(self, mirror_facade, network) -> None:
        self._mirror = mirror_facade
        self._network = network

    def get_piece_at(self, pos: Position):
        return self._mirror.get_piece_at(pos)

    def is_on_cooldown(self, pos: Position) -> bool:
        return self._mirror.is_on_cooldown(pos)

    def is_game_over(self) -> bool:
        return self._mirror.is_game_over()

    def request_move(self, src: Position, dst: Position) -> ActionOutcome:
        env = Envelope(
            type=MessageType.MOVE,
            payload=MovePayload(
                session_token=self._network.session.session_token,
                src_row=src.row, src_col=src.col,
                dst_row=dst.row, dst_col=dst.col,
            ).model_dump(),
        )
        try:
            resp = self._network.request(env, timeout=5.0)
        except Exception as exc:
            return ActionOutcome.fail(_Reason(f"NETWORK_ERROR:{exc}"))
        if resp.type == MessageType.MOVE_ACK and resp.payload.get("status") == "accepted":
            return ActionOutcome.ok()
        reason = resp.payload.get("reason", "unknown")
        return ActionOutcome.fail(_Reason(str(reason).upper()))


class GameScene:
    def __init__(self, network, start_data: dict) -> None:
        self._network = network
        self._game_id = start_data.get("game_id")
        self._my_color = start_data.get("color", "w")
        self._opponent = start_data.get("opponent", "?")
        self._room_id = start_data.get("room_id")

        self._container = build_container(list(DEFAULT_APP_CONFIG.board.default_lines))
        self._facade = self._container.facade
        self._mover = NetworkMoveRequester(self._facade, network)
        self._controller = Controller(self._mover, self._container.mapper)
        self._ui_controller = ControllerOutcomeAdapter(self._controller)

        my_username = network.session.username or "You"
        white_username = my_username if self._my_color == "w" else self._opponent
        black_username = self._opponent if self._my_color == "w" else my_username
        # HudRenderer defaults to generic "WHITE"/"BLACK" panel labels — swap
        # in the real usernames without touching ui/ at all (hud_config is
        # already a per-instance customization point on HudRenderer).
        named_hud_config = replace(
            DEFAULT_APP_CONFIG.hud, white_label=white_username, black_label=black_username
        )

        self._assets = load_ui_assets(DEFAULT_APP_CONFIG)
        self._renderer = CompositeRenderer((
            BoardRenderer(
                board_img=self._assets.board_img,
                frames_by_token=self._assets.frames_by_token,
                fps_by_token=self._assets.fps_by_token,
                cooldown_overlay=self._assets.cooldown_overlay,
                facade=self._facade,
                selection_overlay=self._assets.selection_overlay,
                legal_moves_overlay=self._assets.legal_moves_overlay,
                anim=self._container.anim,
            ),
            HudRenderer(
                panel_bg=self._assets.panel_bg,
                sidebar_w=_SIDEBAR_W,
                moves=self._container.moves,
                scores=self._container.scores,
                banner=self._container.banner,
                hud_config=named_hud_config,
            ),
        ))

        self._clock = AnimationClock()
        self._elapsed_ms = 0
        self._status_line = DEFAULT_APP_CONFIG.status.idle_prompt
        self._game_over = False
        self._resign_btn = Button("Resign", 20, _FRAME_H + 10, 140, 36)
        self._home_btn = Button("Return to Home", CANVAS_W - 220, _FRAME_H + 10, 200, 36)

    # ── Frame lifecycle ──────────────────────────────────────────────

    def update(self):
        """Drains network events, applies them, ticks animation. May return a scene transition."""
        for env in self._network.poll_events():
            if env.type == MessageType.MOVE_BROADCAST:
                self._replay_move(env.payload)
            elif env.type == MessageType.OPPONENT_DISCONNECTED:
                self._set_banner(f"{env.payload['username']} disconnected — waiting...")
            elif env.type == MessageType.DISCONNECT_COUNTDOWN_TICK:
                self._set_banner(f"Opponent reconnecting... {env.payload['seconds_left']}s")
            elif env.type == MessageType.GAME_END:
                self._on_game_end(env.payload)

        delta_ms = self._clock.tick_ms() or DEFAULT_APP_CONFIG.runtime.fallback_frame_ms
        self._elapsed_ms += delta_ms
        if not self._game_over:
            self._facade.tick(delta_ms)
        self._container.anim.tick(delta_ms)
        return None

    def _replay_move(self, payload: dict) -> None:
        src = Position(payload["src_row"], payload["src_col"])
        dst = Position(payload["dst_row"], payload["dst_col"])
        self._facade.request_move(src, dst)

    def _set_banner(self, message: str) -> None:
        self._container.banner.message = message
        self._container.banner.dirty = True

    def _on_game_end(self, payload: dict) -> None:
        self._game_over = True
        if self._my_color == "w":
            before, after = payload["white_elo_before"], payload["white_elo_after"]
        else:
            before, after = payload["black_elo_before"], payload["black_elo_after"]
        self._set_banner(
            f"Game Over — {payload['result']} ({payload['reason']}). "
            f"Your ELO: {before} -> {after}"
        )

    # ── Input ────────────────────────────────────────────────────────

    def on_click(self, x: int, y: int):
        if self._game_over and self._home_btn.contains(x, y):
            return ("home", {})
        if not self._game_over and self._resign_btn.contains(x, y):
            self._resign()
            return None
        if self._game_over:
            return None

        board_x = x - _SIDEBAR_W
        if board_x < 0 or board_x >= _BOARD_SIZE or y < 0 or y >= _BOARD_SIZE:
            return None
        outcome = self._ui_controller.on_click(board_x, y)
        if outcome is None:
            return None
        if outcome.success:
            self._status_line = DEFAULT_APP_CONFIG.status.accepted
        else:
            reason = outcome.reason.name if outcome.reason is not None else "UNKNOWN"
            if reason == "PIECE_ON_COOLDOWN":
                self._status_line = DEFAULT_APP_CONFIG.status.cooldown
            else:
                self._status_line = f"{DEFAULT_APP_CONFIG.status.fallback_prefix}: {reason}"
        return None

    def on_key(self, key: int):
        if self._game_over:
            return ("home", {}) if key != -1 else None
        if key in (ord("r"), ord("R")):
            self._resign()
        return None

    def _resign(self) -> None:
        env = Envelope(
            type=MessageType.RESIGN,
            payload=ResignPayload(session_token=self._network.session.session_token).model_dump(),
        )
        self._network.send(env)

    # ── Render ───────────────────────────────────────────────────────

    def render(self) -> Img:
        selected = self._controller.pending_src
        selected_pos = (selected.row, selected.col) if selected is not None else None
        ctx = RenderContext(
            elapsed_ms=self._elapsed_ms,
            status_line=self._status_line,
            selected_pos=selected_pos,
            legal_targets=tuple(
                (p.row, p.col) for p in self._facade.get_legal_destinations(selected)
            ) if selected is not None else (),
        )
        board_frame = self._renderer.draw(self._assets.board_img.copy(), ctx)
        self._container.moves.dirty = False
        self._container.scores.dirty = False
        self._container.banner.dirty = False

        canvas = _append_bottom_bar(board_frame)
        self._draw_bottom_bar(canvas)
        return canvas

    def _draw_bottom_bar(self, canvas: Img) -> None:
        if self._game_over:
            self._home_btn.draw(canvas)
        else:
            self._resign_btn.draw(canvas)
        canvas.put_text(
            f"You: {self._my_color.upper()} vs {self._opponent}"
            + (f"  [Room {self._room_id}]" if self._room_id else ""),
            240, _FRAME_H + 34, color_bgr=(180, 180, 190), scale=0.5, thickness=1,
        )


def _append_bottom_bar(board_frame: Img) -> Img:
    """
    Extend the rendered frame with a solid-color strip for the control bar.

    NOT done via Img.draw_on (alpha-composite onto a separate canvas):
    board.png has an alpha channel, and HudRenderer pads its sidebars with
    alpha=0 before the sidebar panels are drawn on top of that padding via
    fill_rect/put_text — which never touch the alpha channel. Alpha-
    compositing that result onto another image would treat those pixels as
    fully transparent and silently discard the whole sidebar (this was a
    real bug: HUD panels never appeared, exactly like ui/runtime/game_loop.py
    never re-composites its own output — it hands it to .show() as-is,
    which drops alpha via a straight BGRA->BGR conversion, never blends).
    Padding with cv2 directly avoids alpha semantics entirely.
    """
    pixels = board_frame.pixels
    if pixels.shape[2] == 4:
        pixels = cv2.cvtColor(pixels, cv2.COLOR_BGRA2BGR)
    extended = cv2.copyMakeBorder(pixels, 0, _BAR_H, 0, 0, cv2.BORDER_CONSTANT, value=(18, 18, 22))
    return Img(extended)
