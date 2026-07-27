"""
auth_scene.py — Login / Register form.

Mirrors client/screens/login_screen.py's request flow (LOGIN/REGISTER via
Envelope + ClientSession.request), with cv2 text fields instead of input().
"""
from __future__ import annotations

import numpy as np

from client.gui.widgets import Button, TextField, draw_error
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, LoginPayload, RegisterPayload
from ui.vendor.img import Img

CANVAS_W = 640
CANVAS_H = 480
_BG = (30, 30, 36)


class AuthScene:
    def __init__(self, network, mode: str) -> None:
        assert mode in ("login", "register")
        self._network = network
        self._mode = mode
        cx = CANVAS_W // 2 - 140
        self._username = TextField(cx, 160, 280, 36, label="Username")
        self._password = TextField(cx, 230, 280, 36, label="Password", mask=True)
        self._username.focused = True
        self._fields = [self._username, self._password]
        self._submit = Button("Login" if mode == "login" else "Register", cx, 290, 130, 40)
        self._back = Button("Back", cx + 150, 290, 130, 40)
        self._error: str | None = None
        self._info: str | None = None

    def update(self) -> None:
        pass

    def on_click(self, x: int, y: int):
        for field in self._fields:
            field.focused = field.contains(x, y)
        if self._submit.contains(x, y):
            return self._submit_form()
        if self._back.contains(x, y):
            return ("home", {})
        return None

    def on_key(self, key: int):
        if key == -1:
            return None
        if key == 9:  # Tab — switch focus between fields
            self._username.focused, self._password.focused = self._password.focused, self._username.focused
            return None
        for field in self._fields:
            if field.handle_key(key):
                return self._submit_form()
        return None

    def _submit_form(self):
        username = self._username.value.strip()
        password = self._password.value.strip()
        if not username or not password:
            self._error = "Username and password are required."
            return None

        msg_type = MessageType.LOGIN if self._mode == "login" else MessageType.REGISTER
        payload = (LoginPayload if self._mode == "login" else RegisterPayload)(
            username=username, password=password
        )
        env = Envelope(type=msg_type, payload=payload.model_dump())
        try:
            resp = self._network.request(env, timeout=10.0)
        except Exception as exc:
            self._error = f"Connection error: {exc}"
            return None

        if self._mode == "login":
            if resp.type == MessageType.LOGIN_OK:
                self._network.session.set_auth(
                    resp.payload["session_token"], resp.payload["username"], resp.payload["elo"]
                )
                return ("home", {})
            self._error = f"Login failed: {resp.payload.get('reason', 'unknown')}"
            return None
        else:
            if resp.type == MessageType.REGISTER_OK:
                self._info = "Registered. Please login."
                self._error = None
                return None
            self._error = f"Registration failed: {resp.payload.get('reason', 'unknown')}"
            return None

    def render(self) -> Img:
        canvas = Img(np.full((CANVAS_H, CANVAS_W, 3), _BG, dtype=np.uint8))
        title = "Login" if self._mode == "login" else "Register"
        canvas.put_text(title, CANVAS_W // 2 - 40, 90, color_bgr=(230, 230, 235), scale=0.9, thickness=2)

        for field in self._fields:
            field.draw(canvas)
        self._submit.draw(canvas)
        self._back.draw(canvas)

        if self._error:
            draw_error(canvas, CANVAS_W // 2 - 140, 360, self._error)
        elif self._info:
            canvas.put_text(self._info, CANVAS_W // 2 - 140, 360, color_bgr=(150, 200, 150), scale=0.55, thickness=1)
        return canvas
