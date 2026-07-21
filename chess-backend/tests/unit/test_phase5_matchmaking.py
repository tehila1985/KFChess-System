"""
Phase 5 unit tests: MatchmakingService — pairing rules, timeout, FIFO ordering.

Uses a fake clock and in-memory fake objects so no real sockets needed.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from server.config_loader import load_settings
from server.domain.player import Player
from server.services.matchmaking_service import MatchmakingService, _QueueEntry


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeHub:
    def __init__(self):
        self.sent: dict[str, list] = {}

    async def send(self, conn_id: str, msg: str) -> bool:
        self.sent.setdefault(conn_id, []).append(msg)
        return True

    async def broadcast(self, conn_ids, msg: str):
        for c in conn_ids:
            await self.send(c, msg)


class FakeSession:
    def __init__(self, game_id="g1"):
        self.game_id = game_id
        self.started = False
        self.white = None
        self.black = None

    async def start(self):
        self.started = True


class FakeFactory:
    def __init__(self):
        self.created: list[tuple] = []
        self._counter = 0

    def create(self, white: Player, black: Player, room_id=None) -> FakeSession:
        self._counter += 1
        s = FakeSession(f"game_{self._counter}")
        s.white = white
        s.black = black
        self.created.append((white.username, black.username))
        return s


class FakeGameHandler:
    def __init__(self):
        self.sessions: list = []

    def register_session(self, session):
        self.sessions.append(session)


def make_player(username: str, elo: int, conn_id: str = None) -> Player:
    return Player(
        user_id=hash(username) % 1000,
        username=username,
        elo=elo,
        conn_id=conn_id or f"conn_{username}",
        session_token=f"tok_{username}",
    )


def make_mm(settings=None, factory=None, hub=None, game_handler=None):
    s = settings or load_settings()
    f = factory or FakeFactory()
    h = hub or FakeHub()
    g = game_handler or FakeGameHandler()
    return MatchmakingService(
        settings=s,
        factory=f,
        hub=h,
        game_handler=g,
        logger=logging.getLogger("test"),
    ), f, h, g


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMatchmakingService:
    def test_enqueue_increases_queue_size(self):
        mm, *_ = make_mm()
        mm.enqueue(make_player("alice", 1200))
        assert mm.queue_size() == 1

    def test_dequeue_removes_player(self):
        mm, *_ = make_mm()
        p = make_player("alice", 1200)
        mm.enqueue(p)
        mm.dequeue(p.conn_id)
        assert mm.queue_size() == 0

    def test_double_enqueue_same_player_ignored(self):
        mm, *_ = make_mm()
        p = make_player("alice", 1200)
        mm.enqueue(p)
        mm.enqueue(p)
        assert mm.queue_size() == 1

    @pytest.mark.asyncio
    async def test_pairs_players_within_band(self):
        mm, factory, hub, game_handler = make_mm()
        p1 = make_player("alice", 1200, "c1")
        p2 = make_player("bob", 1250, "c2")
        mm.enqueue(p1)
        mm.enqueue(p2)
        await mm._tick()
        assert len(factory.created) == 1
        assert mm.queue_size() == 0

    @pytest.mark.asyncio
    async def test_does_not_pair_outside_band(self):
        mm, factory, *_ = make_mm()
        p1 = make_player("alice", 1200, "c1")
        p2 = make_player("bob", 1400, "c2")  # 200 ELO diff > 100 band
        mm.enqueue(p1)
        mm.enqueue(p2)
        await mm._tick()
        assert len(factory.created) == 0
        assert mm.queue_size() == 2

    @pytest.mark.asyncio
    async def test_first_enqueued_becomes_white(self):
        mm, factory, hub, game_handler = make_mm()
        first = make_player("alice", 1200, "c1")
        second = make_player("bob", 1200, "c2")
        mm.enqueue(first)
        mm.enqueue(second)
        await mm._tick()
        assert len(factory.created) == 1
        white_name, black_name = factory.created[0]
        assert white_name == "alice"
        assert black_name == "bob"

    @pytest.mark.asyncio
    async def test_timeout_sends_play_timeout(self):
        settings = load_settings()
        mm, factory, hub, _ = make_mm()
        p = make_player("alice", 1200, "c1")
        mm.enqueue(p)
        # Fake the enqueued_at to be in the past
        mm._queue[0].enqueued_at = 0.0  # far in the past
        await mm._tick()
        import json
        msgs = hub.sent.get("c1", [])
        assert any(json.loads(m)["type"] == "PLAY_TIMEOUT" for m in msgs)
        assert mm.queue_size() == 0

    @pytest.mark.asyncio
    async def test_match_found_sends_play_match_found(self):
        mm, factory, hub, _ = make_mm()
        p1 = make_player("alice", 1200, "c1")
        p2 = make_player("bob", 1200, "c2")
        mm.enqueue(p1)
        mm.enqueue(p2)
        await mm._tick()
        import json
        msgs1 = hub.sent.get("c1", [])
        msgs2 = hub.sent.get("c2", [])
        assert any(json.loads(m)["type"] == "PLAY_MATCH_FOUND" for m in msgs1)
        assert any(json.loads(m)["type"] == "PLAY_MATCH_FOUND" for m in msgs2)

    @pytest.mark.asyncio
    async def test_three_players_pairs_two_closest(self):
        """With 3 players, the two closest in ELO should be paired."""
        mm, factory, hub, _ = make_mm()
        p1 = make_player("alice", 1200, "c1")
        p2 = make_player("bob", 1210, "c2")    # 10 diff from alice
        p3 = make_player("charlie", 1280, "c3")  # 80 diff from alice, 70 from bob
        mm.enqueue(p1)
        mm.enqueue(p2)
        mm.enqueue(p3)
        await mm._tick()
        # alice and bob should pair (first two, both in band)
        assert len(factory.created) == 1
        white_name, black_name = factory.created[0]
        assert white_name == "alice"
        assert black_name == "bob"
        # charlie remains
        assert mm.queue_size() == 1

    @pytest.mark.asyncio
    async def test_session_registered_with_game_handler(self):
        mm, factory, hub, game_handler = make_mm()
        p1 = make_player("alice", 1200, "c1")
        p2 = make_player("bob", 1200, "c2")
        mm.enqueue(p1)
        mm.enqueue(p2)
        await mm._tick()
        assert len(game_handler.sessions) == 1
