"""
Unit tests for client/gui/scenes/game_scene.py:NetworkMoveRequester.

Pure logic: reads proxy to the local mirror facade, request_move only
talks to the (fake) network — it never mutates the mirror directly. That
mutation-free contract is the core correctness property of the
server-authoritative-replay design (see the plan): a rejected move must
leave the mirror untouched.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from client.gui.scenes.game_scene import NetworkMoveRequester
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope
from engine.models.position import Position


class FakeMirrorFacade:
    """Records calls; request_move must never be called by the adapter."""

    def __init__(self):
        self.request_move_calls = []

    def get_piece_at(self, pos):
        return f"piece@{pos}"

    def is_on_cooldown(self, pos):
        return pos == Position(1, 1)

    def is_game_over(self):
        return False

    def request_move(self, src, dst):
        self.request_move_calls.append((src, dst))
        raise AssertionError("NetworkMoveRequester must never mutate the mirror directly")


class FakeSession:
    session_token = "tok-123"


class FakeNetwork:
    def __init__(self, response: Envelope):
        self.session = FakeSession()
        self._response = response
        self.sent_envelopes = []

    def request(self, envelope, timeout=5.0):
        self.sent_envelopes.append(envelope)
        return self._response


def test_reads_proxy_to_mirror_facade():
    mirror = FakeMirrorFacade()
    network = FakeNetwork(Envelope(type=MessageType.MOVE_ACK, payload={"status": "accepted"}))
    adapter = NetworkMoveRequester(mirror, network)

    assert adapter.get_piece_at(Position(0, 0)) == "piece@Position(row=0, col=0)"
    assert adapter.is_on_cooldown(Position(1, 1)) is True
    assert adapter.is_on_cooldown(Position(2, 2)) is False
    assert adapter.is_game_over() is False


def test_accepted_move_sends_move_envelope_and_does_not_mutate_mirror():
    mirror = FakeMirrorFacade()
    network = FakeNetwork(Envelope(type=MessageType.MOVE_ACK, payload={"status": "accepted"}))
    adapter = NetworkMoveRequester(mirror, network)

    outcome = adapter.request_move(Position(6, 4), Position(4, 4))

    assert outcome.success is True
    assert len(network.sent_envelopes) == 1
    sent = network.sent_envelopes[0]
    assert sent.type == MessageType.MOVE
    assert sent.payload["session_token"] == "tok-123"
    assert sent.payload == {
        "session_token": "tok-123",
        "src_row": 6, "src_col": 4, "dst_row": 4, "dst_col": 4,
    }
    assert mirror.request_move_calls == []  # never mutated directly


def test_rejected_move_returns_failure_with_reason_and_does_not_mutate_mirror():
    mirror = FakeMirrorFacade()
    network = FakeNetwork(Envelope(
        type=MessageType.MOVE_ACK,
        payload={"status": "rejected", "reason": "not_your_piece"},
    ))
    adapter = NetworkMoveRequester(mirror, network)

    outcome = adapter.request_move(Position(1, 4), Position(2, 4))

    assert outcome.success is False
    assert outcome.reason.name == "NOT_YOUR_PIECE"
    assert mirror.request_move_calls == []


def test_network_error_returns_failure_instead_of_raising():
    mirror = FakeMirrorFacade()

    class RaisingNetwork:
        session = FakeSession()

        def request(self, envelope, timeout=5.0):
            raise TimeoutError("no response")

    adapter = NetworkMoveRequester(mirror, RaisingNetwork())
    outcome = adapter.request_move(Position(6, 4), Position(4, 4))

    assert outcome.success is False
    assert mirror.request_move_calls == []
