"""
Unit tests for client/gui/scenes/game_scene.py:GameScene.

Covers the on_click/on_key/update/render paths not already exercised by
test_gui_network_move_requester.py (which focuses on the NetworkMoveRequester
adapter in isolation).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from client.gui.scenes.game_scene import GameScene, _SIDEBAR_W, _FRAME_H
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope


class FakeSession:
    session_token = "tok"
    username = "alice"
    elo = 1200

    def is_authenticated(self):
        return True


class FakeNetwork:
    def __init__(self):
        self.session = FakeSession()
        self.sent = []
        self._events = []

    def send(self, envelope):
        self.sent.append(envelope)

    def request(self, envelope, timeout=5.0):
        return Envelope(type=MessageType.MOVE_ACK, payload={"status": "accepted"})

    def poll_events(self):
        events = self._events
        self._events = []
        return events


def _make_scene():
    return GameScene(FakeNetwork(), {"game_id": "g1", "color": "w", "opponent": "bob", "room_id": "ROOM1"})


def test_click_outside_board_is_a_no_op():
    scene = _make_scene()
    assert scene.on_click(0, 0) is None


def test_click_selects_own_piece():
    scene = _make_scene()
    x = _SIDEBAR_W + 4 * 100 + 50
    y = 6 * 100 + 50
    scene.on_click(x, y)
    assert scene._controller.pending_src is not None


def test_click_sequence_sends_move_request():
    scene = _make_scene()
    x = _SIDEBAR_W + 4 * 100 + 50
    scene.on_click(x, 6 * 100 + 50)  # select white pawn
    scene.on_click(x, 4 * 100 + 50)  # move it two squares

    assert scene._status_line == "Move accepted"
    assert scene._controller.pending_src is None


def test_resign_button_sends_resign_message():
    scene = _make_scene()
    scene.on_click(scene._resign_btn.x + 1, scene._resign_btn.y + 1)
    assert len(scene._network.sent) == 1
    assert scene._network.sent[0].type == MessageType.RESIGN


def test_resign_keyboard_shortcut():
    scene = _make_scene()
    scene.on_key(ord("r"))
    assert len(scene._network.sent) == 1
    assert scene._network.sent[0].type == MessageType.RESIGN


def test_home_button_only_active_after_game_over():
    scene = _make_scene()
    result = scene.on_click(scene._home_btn.x + 1, scene._home_btn.y + 1)
    assert result is None  # game not over yet — this area is just board/empty

    scene._game_over = True
    result = scene.on_click(scene._home_btn.x + 1, scene._home_btn.y + 1)
    assert result == ("home", {})


def test_on_key_after_game_over_returns_home_on_any_key():
    scene = _make_scene()
    scene._game_over = True
    assert scene.on_key(-1) is None
    assert scene.on_key(ord("x")) == ("home", {})


def test_update_replays_move_broadcast_on_mirror():
    scene = _make_scene()
    scene._network._events.append(Envelope(type=MessageType.MOVE_BROADCAST, payload={
        "src_row": 6, "src_col": 4, "dst_row": 4, "dst_col": 4, "color": "w",
        "board": [], "scores": {"w": 0, "b": 0}, "game_over": False, "winner": None,
    }))
    scene.update()
    # The pawn has left its source square (motion started immediately).
    from engine.models.position import Position
    assert scene._facade.get_piece_at(Position(6, 4)) is not None  # shown in-flight at src


def test_update_sets_banner_on_opponent_disconnected():
    scene = _make_scene()
    scene._network._events.append(Envelope(
        type=MessageType.OPPONENT_DISCONNECTED, payload={"username": "bob"},
    ))
    scene.update()
    assert "bob disconnected" in scene._container.banner.message


def test_update_sets_banner_on_countdown_tick():
    scene = _make_scene()
    scene._network._events.append(Envelope(
        type=MessageType.DISCONNECT_COUNTDOWN_TICK, payload={"seconds_left": 7},
    ))
    scene.update()
    assert "7s" in scene._container.banner.message


def test_update_handles_game_end_as_white():
    scene = _make_scene()
    scene._network._events.append(Envelope(type=MessageType.GAME_END, payload={
        "result": "white", "reason": "resign",
        "white_elo_before": 1200, "white_elo_after": 1216,
        "black_elo_before": 1200, "black_elo_after": 1184,
    }))
    scene.update()
    assert scene._game_over is True
    assert "1200 -> 1216" in scene._container.banner.message


def test_update_handles_game_end_as_black():
    network = FakeNetwork()
    scene = GameScene(network, {"game_id": "g1", "color": "b", "opponent": "bob"})
    network._events.append(Envelope(type=MessageType.GAME_END, payload={
        "result": "white", "reason": "checkmate",
        "white_elo_before": 1200, "white_elo_after": 1216,
        "black_elo_before": 1200, "black_elo_after": 1184,
    }))
    scene.update()
    assert "1200 -> 1184" in scene._container.banner.message


def test_render_before_and_after_game_over_does_not_raise():
    scene = _make_scene()
    frame = scene.render()
    assert frame.pixels.shape[1] > 0

    scene._game_over = True
    scene.render()
