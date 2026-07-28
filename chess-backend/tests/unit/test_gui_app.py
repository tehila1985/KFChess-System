"""
Unit tests for client/gui/app.py.

App.run() itself opens a real cv2 window and blocks in an event loop —
not testable headlessly (no display in CI). This covers what's pure
logic: scene dispatch and mouse-event bookkeeping.
"""
from __future__ import annotations

import os
import sys

import cv2
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from client.gui.app import App, _build_scene
from client.gui.scenes.auth_scene import AuthScene
from client.gui.scenes.game_scene import GameScene
from client.gui.scenes.home_scene import HomeScene
from client.gui.scenes.play_scene import PlayScene
from client.gui.scenes.room_scene import RoomScene


class FakeSession:
    session_token = "tok"
    username = "alice"
    elo = 1200

    def is_authenticated(self):
        return False


class FakeNetwork:
    def __init__(self):
        self.session = FakeSession()
        self.stopped = False

    def send(self, envelope):
        pass

    def poll_events(self):
        return []

    def stop(self):
        self.stopped = True


@pytest.mark.parametrize("name,expected_type", [
    ("home", HomeScene),
    ("login", AuthScene),
    ("register", AuthScene),
    ("play", PlayScene),
    ("room", RoomScene),
])
def test_build_scene_dispatches_by_name(name, expected_type):
    scene = _build_scene(name, {}, FakeNetwork())
    assert isinstance(scene, expected_type)


def test_build_scene_game_passes_start_data():
    data = {"game_id": "g1", "color": "w", "opponent": "bob"}
    scene = _build_scene("game", data, FakeNetwork())
    assert isinstance(scene, GameScene)
    assert scene._game_id == "g1"


def test_build_scene_unknown_name_raises():
    with pytest.raises(ValueError):
        _build_scene("nonsense", {}, FakeNetwork())


def test_app_starts_on_home_scene():
    app = App(FakeNetwork())
    assert isinstance(app._scene, HomeScene)


def test_on_mouse_left_button_down_records_click():
    app = App(FakeNetwork())
    app._on_mouse(cv2.EVENT_LBUTTONDOWN, 42, 84, 0, None)
    assert app._click_state == {"x": 42, "y": 84, "clicked": True}


def test_on_mouse_ignores_other_events():
    app = App(FakeNetwork())
    app._on_mouse(cv2.EVENT_MOUSEMOVE, 1, 2, 0, None)
    assert app._click_state["clicked"] is False
