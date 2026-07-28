"""
Unit tests for client/gui/scenes/room_scene.py.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from client.gui.scenes.room_scene import RoomScene
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope


class FakeSession:
    session_token = "tok-1"


class FakeNetwork:
    def __init__(self, response=None, raise_exc=None):
        self.session = FakeSession()
        self._response = response
        self._raise = raise_exc
        self._events = []
        self.sent_envelopes = []

    def request(self, envelope, timeout=10.0):
        self.sent_envelopes.append(envelope)
        if self._raise is not None:
            raise self._raise
        return self._response

    def poll_events(self):
        events = self._events
        self._events = []
        return events


def test_create_room_success_moves_to_waiting():
    network = FakeNetwork(response=Envelope(type=MessageType.ROOM_CREATED, payload={"room_id": "ABC123"}))
    scene = RoomScene(network)

    scene.on_click(scene._create_btn.x + 1, scene._create_btn.y + 1)

    assert scene._state == "waiting"
    assert scene._room_id == "ABC123"
    assert scene._role == "white"
    assert network.sent_envelopes[0].type == MessageType.ROOM_CREATE


def test_create_room_error_shows_reason():
    network = FakeNetwork(response=Envelope(type=MessageType.ROOM_ERROR, payload={"reason": "boom"}))
    scene = RoomScene(network)

    scene.on_click(scene._create_btn.x + 1, scene._create_btn.y + 1)

    assert scene._state == "choose"
    assert "boom" in scene._error


def test_create_room_network_exception_shows_error():
    network = FakeNetwork(raise_exc=RuntimeError("offline"))
    scene = RoomScene(network)

    scene.on_click(scene._create_btn.x + 1, scene._create_btn.y + 1)

    assert scene._error == "offline"
    assert scene._state == "choose"


def test_join_button_switches_to_input_state():
    scene = RoomScene(FakeNetwork())
    scene.on_click(scene._join_btn.x + 1, scene._join_btn.y + 1)
    assert scene._state == "join_input"
    assert scene._room_id_field.focused is True


def test_join_room_success_moves_to_waiting():
    network = FakeNetwork(response=Envelope(
        type=MessageType.ROOM_ROLE_ASSIGNED, payload={"role": "black"},
    ))
    scene = RoomScene(network)
    scene.on_click(scene._join_btn.x + 1, scene._join_btn.y + 1)
    for ch in "xyz789":
        scene._room_id_field.handle_key(ord(ch))

    scene.on_click(scene._submit_join.x + 1, scene._submit_join.y + 1)

    assert scene._state == "waiting"
    assert scene._room_id == "XYZ789"
    assert scene._role == "black"
    join_env = network.sent_envelopes[0]
    assert join_env.type == MessageType.ROOM_JOIN
    assert join_env.payload["room_id"] == "XYZ789"


def test_join_room_with_empty_id_shows_error_without_network_call():
    network = FakeNetwork()
    scene = RoomScene(network)
    scene.on_click(scene._join_btn.x + 1, scene._join_btn.y + 1)

    scene.on_click(scene._submit_join.x + 1, scene._submit_join.y + 1)

    assert scene._error == "Enter a room ID."
    assert network.sent_envelopes == []


def test_join_room_error_response_shows_reason():
    network = FakeNetwork(response=Envelope(type=MessageType.ROOM_ERROR, payload={"reason": "room_not_found"}))
    scene = RoomScene(network)
    scene.on_click(scene._join_btn.x + 1, scene._join_btn.y + 1)
    for ch in "badid1":
        scene._room_id_field.handle_key(ord(ch))

    scene.on_click(scene._submit_join.x + 1, scene._submit_join.y + 1)

    assert scene._state == "join_input"
    assert "room_not_found" in scene._error


def test_enter_key_in_join_input_submits():
    network = FakeNetwork(response=Envelope(type=MessageType.ROOM_ROLE_ASSIGNED, payload={"role": "black"}))
    scene = RoomScene(network)
    scene.on_click(scene._join_btn.x + 1, scene._join_btn.y + 1)
    for ch in "abc123":
        scene._room_id_field.handle_key(ord(ch))

    scene.on_key(13)

    assert scene._state == "waiting"


def test_back_button_returns_home():
    scene = RoomScene(FakeNetwork())
    result = scene.on_click(scene._back_btn.x + 1, scene._back_btn.y + 1)
    assert result == ("home", {})


def test_update_only_polls_while_waiting():
    network = FakeNetwork()
    scene = RoomScene(network)
    network._events.append(Envelope(type=MessageType.GAME_START, payload={"game_id": "g1"}))
    # Still in "choose" state — must not consume/transition on this event.
    assert scene.update() is None


def test_update_returns_game_transition_once_waiting():
    network = FakeNetwork(response=Envelope(type=MessageType.ROOM_CREATED, payload={"room_id": "ABC123"}))
    scene = RoomScene(network)
    scene.on_click(scene._create_btn.x + 1, scene._create_btn.y + 1)
    start_payload = {"game_id": "g1", "room_id": "ABC123"}
    network._events.append(Envelope(type=MessageType.GAME_START, payload=start_payload))

    result = scene.update()

    assert result == ("game", start_payload)


def test_render_all_states_do_not_raise():
    network = FakeNetwork(response=Envelope(type=MessageType.ROOM_CREATED, payload={"room_id": "ABC123"}))
    scene = RoomScene(network)
    scene.render()  # choose
    scene._state = "join_input"
    scene.render()
    scene._state = "waiting"
    scene._room_id = "ABC123"
    scene._role = "white"
    scene.render()
    scene._error = "boom"
    scene.render()
