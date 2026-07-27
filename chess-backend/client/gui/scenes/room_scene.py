"""
room_scene.py — create/join a room, pin the room ID, wait for GAME_START.

Mirrors client/screens/room_screen.py's flow.
"""
from __future__ import annotations

import numpy as np

from client.gui.widgets import Button, TextField, draw_error
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, RoomCreatePayload, RoomJoinPayload
from ui.vendor.img import Img

CANVAS_W = 640
CANVAS_H = 480
_BG = (30, 30, 36)

# Sub-states within this scene.
_CHOOSE = "choose"
_JOIN_INPUT = "join_input"
_WAITING = "waiting"


class RoomScene:
    def __init__(self, network) -> None:
        self._network = network
        self._state = _CHOOSE
        self._error: str | None = None
        self._room_id: str | None = None
        self._role: str | None = None

        cx = CANVAS_W // 2 - 100
        self._create_btn = Button("Create Room", cx, 180, 200, 44)
        self._join_btn = Button("Join Room", cx, 234, 200, 44)
        self._back_btn = Button("Back", cx, 300, 200, 40)

        self._room_id_field = TextField(CANVAS_W // 2 - 90, 200, 180, 36, label="Room ID")
        self._submit_join = Button("Join", CANVAS_W // 2 - 100, 260, 200, 40)

    def update(self):
        """Returns a scene transition once GAME_START arrives, else None."""
        if self._state != _WAITING:
            return None
        for env in self._network.poll_events():
            if env.type == MessageType.GAME_START:
                return ("game", env.payload)
        return None

    def on_click(self, x: int, y: int):
        if self._state == _CHOOSE:
            if self._create_btn.contains(x, y):
                self._create_room()
                return None
            if self._join_btn.contains(x, y):
                self._state = _JOIN_INPUT
                self._room_id_field.focused = True
                return None
            if self._back_btn.contains(x, y):
                return ("home", {})
            return None

        if self._state == _JOIN_INPUT:
            self._room_id_field.focused = self._room_id_field.contains(x, y)
            if self._submit_join.contains(x, y):
                self._join_room()
            return None

        return None

    def on_key(self, key: int):
        if self._state == _JOIN_INPUT:
            if self._room_id_field.handle_key(key):
                self._join_room()
        return None

    def _create_room(self) -> None:
        session = self._network.session
        env = Envelope(
            type=MessageType.ROOM_CREATE,
            payload=RoomCreatePayload(session_token=session.session_token).model_dump(),
        )
        try:
            resp = self._network.request(env, timeout=10.0)
        except Exception as exc:
            self._error = str(exc)
            return
        if resp.type != MessageType.ROOM_CREATED:
            self._error = f"Error: {resp.payload.get('reason', 'unknown')}"
            return
        self._room_id = resp.payload["room_id"]
        self._role = "white"
        self._state = _WAITING

    def _join_room(self) -> None:
        room_id = self._room_id_field.value.strip().upper()
        if not room_id:
            self._error = "Enter a room ID."
            return
        session = self._network.session
        env = Envelope(
            type=MessageType.ROOM_JOIN,
            payload=RoomJoinPayload(session_token=session.session_token, room_id=room_id).model_dump(),
        )
        try:
            resp = self._network.request(env, timeout=10.0)
        except Exception as exc:
            self._error = str(exc)
            return
        if resp.type == MessageType.ROOM_ERROR:
            self._error = f"Error: {resp.payload.get('reason', 'unknown')}"
            return
        self._room_id = room_id
        self._role = resp.payload.get("role", "?")
        self._state = _WAITING

    def render(self) -> Img:
        canvas = Img(np.full((CANVAS_H, CANVAS_W, 3), _BG, dtype=np.uint8))
        canvas.put_text("Room", CANVAS_W // 2 - 40, 90, color_bgr=(230, 230, 235), scale=0.9, thickness=2)

        if self._state == _CHOOSE:
            self._create_btn.draw(canvas)
            self._join_btn.draw(canvas)
            self._back_btn.draw(canvas)
        elif self._state == _JOIN_INPUT:
            self._room_id_field.draw(canvas)
            self._submit_join.draw(canvas)
        elif self._state == _WAITING:
            canvas.put_text(f"Room ID: {self._room_id}", CANVAS_W // 2 - 100, 180,
                             color_bgr=(100, 210, 255), scale=0.75, thickness=2)
            canvas.put_text(f"Role: {self._role}", CANVAS_W // 2 - 100, 220,
                             color_bgr=(200, 200, 210), scale=0.55, thickness=1)
            canvas.put_text("Waiting for opponent...", CANVAS_W // 2 - 130, 260,
                             color_bgr=(180, 180, 190), scale=0.55, thickness=1)

        if self._error:
            draw_error(canvas, CANVAS_W // 2 - 140, 400, self._error)
        return canvas
