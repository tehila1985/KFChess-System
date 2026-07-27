"""
app.py — top-level scene loop for the networked GUI client.

One cv2 window, one mouse callback, one keyboard poll — mirrors the loop
shape in ui/runtime/game_loop.py. The active "scene" object owns its own
input/update/render logic (duck-typed: on_click, on_key, update, render)
and can return (next_scene_name, data) to switch scenes, or None to keep
running as-is.
"""
from __future__ import annotations

import cv2

from client.gui.network_client import NetworkClient
from client.gui.scenes.auth_scene import AuthScene
from client.gui.scenes.game_scene import GameScene
from client.gui.scenes.home_scene import HomeScene
from client.gui.scenes.play_scene import PlayScene
from client.gui.scenes.room_scene import RoomScene

WINDOW_TITLE = "Chess - Online"


def _build_scene(name: str, data: dict, network: NetworkClient):
    if name == "home":
        return HomeScene(network)
    if name == "login":
        return AuthScene(network, mode="login")
    if name == "register":
        return AuthScene(network, mode="register")
    if name == "play":
        return PlayScene(network)
    if name == "room":
        return RoomScene(network)
    if name == "game":
        return GameScene(network, data)
    raise ValueError(f"unknown scene: {name}")


class App:
    def __init__(self, network: NetworkClient) -> None:
        self._network = network
        self._click_state = {"x": None, "y": None, "clicked": False}
        self._scene = HomeScene(network)

    def _on_mouse(self, event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            self._click_state["x"] = x
            self._click_state["y"] = y
            self._click_state["clicked"] = True

    def run(self) -> None:
        cv2.namedWindow(WINDOW_TITLE)
        cv2.setMouseCallback(WINDOW_TITLE, self._on_mouse)
        key = -1

        try:
            while True:
                transition = None

                if self._click_state["clicked"]:
                    x = int(self._click_state["x"])
                    y = int(self._click_state["y"])
                    self._click_state["clicked"] = False
                    transition = self._scene.on_click(x, y)

                if transition is None:
                    transition = self._scene.update()

                if transition is None and key != -1:
                    transition = self._scene.on_key(key)

                if transition is not None:
                    name, data = transition
                    if name == "quit":
                        break
                    self._scene = _build_scene(name, data, self._network)

                frame = self._scene.render()
                key = frame.show(WINDOW_TITLE)

                if cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            cv2.destroyAllWindows()
            self._network.stop()
