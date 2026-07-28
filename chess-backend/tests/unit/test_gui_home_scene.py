"""
Unit tests for client/gui/scenes/home_scene.py.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from client.gui.scenes.home_scene import HomeScene


class FakeSession:
    def __init__(self, authenticated=False, username="alice", elo=1200):
        self._authenticated = authenticated
        self.username = username
        self.elo = elo

    def is_authenticated(self):
        return self._authenticated


class FakeNetwork:
    def __init__(self, authenticated=False):
        self.session = FakeSession(authenticated=authenticated)


def _click(scene, name):
    """Click the center of the named button."""
    for btn_name, button in scene._buttons:
        if btn_name == name:
            return scene.on_click(button.x + 5, button.y + 5)
    raise AssertionError(f"no button named {name}")


def test_login_and_register_available_when_logged_out():
    scene = HomeScene(FakeNetwork(authenticated=False))
    assert _click(scene, "login") == ("login", {})
    assert _click(scene, "register") == ("register", {})


def test_play_and_room_blocked_when_not_authenticated():
    scene = HomeScene(FakeNetwork(authenticated=False))
    assert _click(scene, "play") is None
    assert scene._error is not None
    assert _click(scene, "room") is None


def test_play_and_room_available_when_authenticated():
    scene = HomeScene(FakeNetwork(authenticated=True))
    assert _click(scene, "play") == ("play", {})
    assert _click(scene, "room") == ("room", {})


def test_quit_button():
    scene = HomeScene(FakeNetwork())
    assert _click(scene, "quit") == ("quit", {})


def test_click_outside_any_button_returns_none():
    scene = HomeScene(FakeNetwork())
    assert scene.on_click(0, 0) is None


def test_on_key_is_a_no_op():
    scene = HomeScene(FakeNetwork())
    assert scene.on_key(ord("q")) is None


def test_render_logged_out_does_not_raise():
    scene = HomeScene(FakeNetwork(authenticated=False))
    frame = scene.render()
    assert frame.pixels.shape[2] == 3


def test_render_logged_in_does_not_raise():
    scene = HomeScene(FakeNetwork(authenticated=True))
    frame = scene.render()
    assert frame.pixels.shape[2] == 3


def test_render_shows_error_banner_after_blocked_click():
    scene = HomeScene(FakeNetwork(authenticated=False))
    _click(scene, "play")
    scene.render()  # must not raise with an active error message
