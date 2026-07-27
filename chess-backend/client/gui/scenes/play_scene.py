"""
play_scene.py — matchmaking: send PLAY_REQUEST, show "Searching...",
transition to the game scene once GAME_START arrives.

Mirrors client/screens/play_screen.py's flow.
"""
from __future__ import annotations

import time

import numpy as np

from client.gui.widgets import Button
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, PlayRequestPayload
from ui.vendor.img import Img

CANVAS_W = 640
CANVAS_H = 480
_BG = (30, 30, 36)


class PlayScene:
    def __init__(self, network) -> None:
        self._network = network
        self._start = time.monotonic()
        self._timed_out = False
        self._error: str | None = None
        self._cancel = Button("Cancel", CANVAS_W // 2 - 65, 340, 130, 40)

        session = network.session
        env = Envelope(
            type=MessageType.PLAY_REQUEST,
            payload=PlayRequestPayload(session_token=session.session_token).model_dump(),
        )
        try:
            network.send(env)
        except Exception as exc:
            self._error = str(exc)

    def update(self):
        """Returns a scene transition once GAME_START arrives, else None."""
        for env in self._network.poll_events():
            if env.type == MessageType.PLAY_TIMEOUT:
                self._timed_out = True
            elif env.type == MessageType.GAME_START:
                return ("game", env.payload)
        return None

    def on_click(self, x: int, y: int):
        if self._cancel.contains(x, y):
            env = Envelope(type=MessageType.PLAY_CANCEL, payload={})
            self._network.send(env)
            return ("home", {})
        return None

    def on_key(self, key: int):
        return None

    def render(self) -> Img:
        canvas = Img(np.full((CANVAS_H, CANVAS_W, 3), _BG, dtype=np.uint8))
        if self._timed_out:
            canvas.put_text("Could not find an opponent.", CANVAS_W // 2 - 170, 220,
                             color_bgr=(90, 90, 240), scale=0.6, thickness=1)
            canvas.put_text("Click Cancel to return.", CANVAS_W // 2 - 130, 250,
                             color_bgr=(180, 180, 190), scale=0.5, thickness=1)
        elif self._error:
            canvas.put_text(f"Error: {self._error}", CANVAS_W // 2 - 170, 220,
                             color_bgr=(90, 90, 240), scale=0.55, thickness=1)
        else:
            elapsed = int(time.monotonic() - self._start)
            canvas.put_text(f"Searching for opponent... {elapsed}s", CANVAS_W // 2 - 170, 220,
                             color_bgr=(230, 230, 235), scale=0.6, thickness=1)
        self._cancel.draw(canvas)
        return canvas
