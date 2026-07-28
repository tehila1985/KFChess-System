"""
Unit tests for client/gui/scenes/play_scene.py.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from client.gui.scenes.play_scene import PlayScene
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope


class FakeSession:
    session_token = "tok-1"


class FakeNetwork:
    def __init__(self, send_exc=None):
        self.session = FakeSession()
        self.sent = []
        self._events = []
        self._send_exc = send_exc

    def send(self, envelope):
        if self._send_exc is not None:
            raise self._send_exc
        self.sent.append(envelope)

    def poll_events(self):
        events = self._events
        self._events = []
        return events


def test_sends_play_request_on_construction():
    network = FakeNetwork()
    PlayScene(network)
    assert len(network.sent) == 1
    assert network.sent[0].type == MessageType.PLAY_REQUEST
    assert network.sent[0].payload["session_token"] == "tok-1"


def test_send_failure_is_captured_as_error():
    network = FakeNetwork(send_exc=RuntimeError("no connection"))
    scene = PlayScene(network)
    assert scene._error == "no connection"


def test_update_sets_timed_out_on_play_timeout():
    network = FakeNetwork()
    scene = PlayScene(network)
    network._events.append(Envelope(type=MessageType.PLAY_TIMEOUT, payload={}))

    result = scene.update()

    assert result is None
    assert scene._timed_out is True


def test_update_returns_game_transition_on_game_start():
    network = FakeNetwork()
    scene = PlayScene(network)
    start_payload = {"game_id": "g1", "color": "w", "opponent": "bob"}
    network._events.append(Envelope(type=MessageType.GAME_START, payload=start_payload))

    result = scene.update()

    assert result == ("game", start_payload)


def test_update_with_no_events_returns_none():
    network = FakeNetwork()
    scene = PlayScene(network)
    assert scene.update() is None


def test_cancel_button_sends_play_cancel_and_returns_home():
    network = FakeNetwork()
    scene = PlayScene(network)
    network.sent.clear()

    result = scene.on_click(scene._cancel.x + 1, scene._cancel.y + 1)

    assert result == ("home", {})
    assert network.sent[0].type == MessageType.PLAY_CANCEL


def test_click_outside_cancel_button_is_a_no_op():
    network = FakeNetwork()
    scene = PlayScene(network)
    assert scene.on_click(0, 0) is None


def test_on_key_is_a_no_op():
    scene = PlayScene(FakeNetwork())
    assert scene.on_key(ord("x")) is None


def test_render_searching_timed_out_and_error_states_do_not_raise():
    network = FakeNetwork()
    scene = PlayScene(network)
    scene.render()

    scene._timed_out = True
    scene.render()

    scene._timed_out = False
    scene._error = "boom"
    scene.render()
