"""
home_scene.py — top-level menu: Login / Register / Play / Room / Quit.

Mirrors client/screens/home_screen.py's menu, drawn with cv2 widgets
instead of printed text.
"""
from __future__ import annotations

import numpy as np

from client.gui.widgets import Button, draw_error
from ui.vendor.img import Img

CANVAS_W = 640
CANVAS_H = 480
_BG = (30, 30, 36)


class HomeScene:
    def __init__(self, network) -> None:
        self._network = network
        self._error: str | None = None
        cx = CANVAS_W // 2 - 100
        self._buttons = [
            ("login", Button("Login", cx, 160, 200, 44)),
            ("register", Button("Register", cx, 214, 200, 44)),
            ("play", Button("Play", cx, 268, 200, 44)),
            ("room", Button("Room", cx, 322, 200, 44)),
            ("quit", Button("Quit", cx, 376, 200, 44)),
        ]

    def update(self) -> None:
        pass

    def on_click(self, x: int, y: int):
        session = self._network.session
        for name, button in self._buttons:
            if not button.contains(x, y):
                continue
            if name in ("play", "room") and not session.is_authenticated():
                self._error = "You must be logged in first."
                return None
            self._error = None
            return (name, {})
        return None

    def on_key(self, key: int):
        return None

    def render(self) -> Img:
        canvas = Img(np.full((CANVAS_H, CANVAS_W, 3), _BG, dtype=np.uint8))
        canvas.put_text("Chess Online", CANVAS_W // 2 - 90, 70, color_bgr=(230, 230, 235), scale=1.1, thickness=2)

        session = self._network.session
        if session.is_authenticated():
            status = f"Logged in as {session.username} (ELO: {session.elo})"
        else:
            status = "Not logged in"
        canvas.put_text(status, CANVAS_W // 2 - 140, 110, color_bgr=(150, 200, 150), scale=0.55, thickness=1)

        for _, button in self._buttons:
            button.draw(canvas)

        if self._error:
            draw_error(canvas, CANVAS_W // 2 - 140, 440, self._error)
        return canvas
