"""
Unit tests for server/directories/ — the Phase 0 seams (see
.github/Server_Design_Implementation_Plan.md) that Phase 1 will back with
Redis without changing MatchmakingService/RoomService call sites.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.connection_hub import ConnectionHub
from server.directories.base import (
    AbstractConnectionDirectory,
    AbstractMatchQueue,
    AbstractRoomRegistry,
)
from server.directories.in_memory import InMemoryMatchQueue, InMemoryRoomRegistry
from server.domain.player import Player
from server.domain.room import Room


def make_player(username: str, elo: int, conn_id: str) -> Player:
    return Player(user_id=1, username=username, elo=elo, conn_id=conn_id, session_token="tok-" + conn_id)


class TestConnectionHubIsAConnectionDirectory:
    def test_connection_hub_satisfies_the_interface(self):
        assert isinstance(ConnectionHub(), AbstractConnectionDirectory)


class TestInMemoryMatchQueue:
    def test_satisfies_interface(self):
        assert isinstance(InMemoryMatchQueue(), AbstractMatchQueue)

    def test_enqueue_dequeue_and_size(self):
        q = InMemoryMatchQueue()
        q.enqueue(make_player("alice", 1200, "c1"))
        assert q.size() == 1
        q.dequeue("c1")
        assert q.size() == 0

    def test_enqueue_same_conn_id_twice_is_a_no_op(self):
        q = InMemoryMatchQueue()
        q.enqueue(make_player("alice", 1200, "c1"))
        q.enqueue(make_player("alice", 1200, "c1"))
        assert q.size() == 1

    def test_pairs_within_range_removes_matched_players(self):
        q = InMemoryMatchQueue()
        a, b = make_player("alice", 1200, "c1"), make_player("bob", 1210, "c2")
        q.enqueue(a)
        q.enqueue(b)
        pairs = q.pairs_within_range(match_range=50)
        assert pairs == [(a, b)]
        assert q.size() == 0

    def test_pairs_within_range_leaves_out_of_range_players_queued(self):
        q = InMemoryMatchQueue()
        a, b = make_player("alice", 1200, "c1"), make_player("bob", 1600, "c2")
        q.enqueue(a)
        q.enqueue(b)
        pairs = q.pairs_within_range(match_range=50)
        assert pairs == []
        assert q.size() == 2

    def test_pop_expired_removes_only_stale_entries(self):
        q = InMemoryMatchQueue()
        q.enqueue(make_player("alice", 1200, "c1"))
        q._queue[0].enqueued_at = 0.0  # far in the past
        q.enqueue(make_player("bob", 1200, "c2"))
        expired = q.pop_expired(timeout_seconds=1.0)
        assert [p.username for p in expired] == ["alice"]
        assert q.size() == 1


class TestInMemoryRoomRegistry:
    def test_satisfies_interface(self):
        assert isinstance(InMemoryRoomRegistry(), AbstractRoomRegistry)

    def test_create_get_exists(self):
        reg = InMemoryRoomRegistry()
        owner = make_player("alice", 1200, "c1")
        room = Room(room_id="ABC12", owner=owner, white=owner)
        assert not reg.exists("ABC12")
        reg.create(room)
        assert reg.exists("ABC12")
        assert reg.get("ABC12") is room

    def test_get_missing_room_returns_none(self):
        reg = InMemoryRoomRegistry()
        assert reg.get("NOPE") is None

    def test_save_is_a_no_op_but_does_not_raise(self):
        reg = InMemoryRoomRegistry()
        owner = make_player("alice", 1200, "c1")
        room = Room(room_id="ABC12", owner=owner, white=owner)
        reg.create(room)
        room.game_id = "g1"
        reg.save(room)
        assert reg.get("ABC12").game_id == "g1"
