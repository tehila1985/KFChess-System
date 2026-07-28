"""
Unit tests for client/gui/scenes/auth_scene.py.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from client.gui.scenes.auth_scene import AuthScene
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope


class FakeSession:
    def __init__(self):
        self.auth_calls = []

    def set_auth(self, token, username, elo):
        self.auth_calls.append((token, username, elo))


class FakeNetwork:
    def __init__(self, response=None, raise_exc=None):
        self.session = FakeSession()
        self._response = response
        self._raise = raise_exc
        self.sent_envelopes = []

    def request(self, envelope, timeout=10.0):
        self.sent_envelopes.append(envelope)
        if self._raise is not None:
            raise self._raise
        return self._response


def _type(scene, field, text):
    field.focused = True
    for ch in text:
        field.handle_key(ord(ch))


def test_login_success_sets_auth_and_returns_home():
    network = FakeNetwork(response=Envelope(
        type=MessageType.LOGIN_OK,
        payload={"session_token": "tok", "username": "alice", "elo": 1200},
    ))
    scene = AuthScene(network, mode="login")
    _type(scene, scene._username, "alice")
    _type(scene, scene._password, "secret123")

    result = scene._submit_form()

    assert result == ("home", {})
    assert network.session.auth_calls == [("tok", "alice", 1200)]
    assert network.sent_envelopes[0].type == MessageType.LOGIN


def test_login_failure_sets_error_and_stays():
    network = FakeNetwork(response=Envelope(
        type=MessageType.LOGIN_ERROR, payload={"reason": "invalid_credentials"},
    ))
    scene = AuthScene(network, mode="login")
    _type(scene, scene._username, "alice")
    _type(scene, scene._password, "wrong")

    result = scene._submit_form()

    assert result is None
    assert "invalid_credentials" in scene._error
    assert network.session.auth_calls == []


def test_register_success_shows_info_message():
    network = FakeNetwork(response=Envelope(type=MessageType.REGISTER_OK, payload={"username": "bob"}))
    scene = AuthScene(network, mode="register")
    _type(scene, scene._username, "bob")
    _type(scene, scene._password, "password123")

    result = scene._submit_form()

    assert result is None
    assert scene._info == "Registered. Please login."
    assert scene._error is None
    assert network.sent_envelopes[0].type == MessageType.REGISTER


def test_register_failure_sets_error():
    network = FakeNetwork(response=Envelope(
        type=MessageType.REGISTER_ERROR, payload={"reason": "username_taken"},
    ))
    scene = AuthScene(network, mode="register")
    _type(scene, scene._username, "bob")
    _type(scene, scene._password, "password123")

    result = scene._submit_form()

    assert result is None
    assert "username_taken" in scene._error


def test_empty_fields_rejected_without_network_call():
    network = FakeNetwork(response=None)
    scene = AuthScene(network, mode="login")

    result = scene._submit_form()

    assert result is None
    assert scene._error == "Username and password are required."
    assert network.sent_envelopes == []


def test_network_exception_is_caught_and_shown_as_error():
    network = FakeNetwork(raise_exc=TimeoutError("no response"))
    scene = AuthScene(network, mode="login")
    _type(scene, scene._username, "alice")
    _type(scene, scene._password, "secret123")

    result = scene._submit_form()

    assert result is None
    assert "Connection error" in scene._error


def test_on_click_submit_button_submits_form():
    network = FakeNetwork(response=Envelope(
        type=MessageType.LOGIN_OK, payload={"session_token": "t", "username": "a", "elo": 1200},
    ))
    scene = AuthScene(network, mode="login")
    _type(scene, scene._username, "alice")
    _type(scene, scene._password, "secret123")

    result = scene.on_click(scene._submit.x + 1, scene._submit.y + 1)

    assert result == ("home", {})


def test_on_click_back_button_returns_home_without_network_call():
    network = FakeNetwork()
    scene = AuthScene(network, mode="login")

    result = scene.on_click(scene._back.x + 1, scene._back.y + 1)

    assert result == ("home", {})
    assert network.sent_envelopes == []


def test_on_click_focuses_clicked_field():
    scene = AuthScene(FakeNetwork(), mode="login")
    scene.on_click(scene._password.x + 1, scene._password.y + 1)
    assert scene._password.focused is True
    assert scene._username.focused is False


def test_tab_key_switches_focus():
    scene = AuthScene(FakeNetwork(), mode="login")
    assert scene._username.focused is True
    scene.on_key(9)
    assert scene._username.focused is False
    assert scene._password.focused is True


def test_enter_key_in_password_field_submits():
    network = FakeNetwork(response=Envelope(
        type=MessageType.LOGIN_OK, payload={"session_token": "t", "username": "a", "elo": 1200},
    ))
    scene = AuthScene(network, mode="login")
    scene._username.focused = True
    _type(scene, scene._username, "alice")
    scene._password.focused = True
    _type(scene, scene._password, "secret123")

    result = scene.on_key(13)

    assert result == ("home", {})


def test_no_key_is_a_no_op():
    scene = AuthScene(FakeNetwork(), mode="login")
    assert scene.on_key(-1) is None


def test_render_login_and_register_do_not_raise():
    for mode in ("login", "register"):
        scene = AuthScene(FakeNetwork(), mode=mode)
        frame = scene.render()
        assert frame.pixels.shape[2] == 3


def test_render_with_error_and_info_do_not_raise():
    scene = AuthScene(FakeNetwork(), mode="login")
    scene._error = "boom"
    scene.render()
    scene._error = None
    scene._info = "ok"
    scene.render()
