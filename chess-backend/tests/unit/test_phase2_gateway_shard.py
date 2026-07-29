"""
Unit tests for the pure-logic pieces added in Phase 2 of
.github/Server_Design_Implementation_Plan.md: GameAllocator,
NatsPublishingConnectionDirectory, and GameHandler.reconnect/
get_session_by_user_id. The full Gateway/Shard network split itself is
covered by tests/e2e/test_phase2_gateway_shard_e2e.py (real subprocesses,
real NATS/Redis) — these are the parts testable without any of that infra.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.allocator import GameAllocator
from server.directories.nats_backed import NatsPublishingConnectionDirectory
from server.domain.player import Player
from server.handlers.game_handler import GameHandler
from server.services.auth_service import AuthService
from server.services.game_session import GameSession
from server.services.rating_service import RatingService
from server.config_loader import load_settings


# ── GameAllocator ────────────────────────────────────────────────────────

class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def set(self, key, value, ex=None):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


class TestGameAllocator:
    def test_allocate_writes_game_to_shard_mapping(self):
        redis_client = FakeRedis()
        allocator = GameAllocator(redis_client, shard_id="shard-7")
        result = allocator.allocate("game-1")
        assert result == "shard-7"
        assert redis_client.store["game:game-1"] == "shard-7"

    def test_shard_for_returns_allocated_shard(self):
        redis_client = FakeRedis()
        allocator = GameAllocator(redis_client, shard_id="shard-7")
        allocator.allocate("game-1")
        assert allocator.shard_for("game-1") == "shard-7"

    def test_shard_for_unknown_game_falls_back_to_own_shard_id(self):
        redis_client = FakeRedis()
        allocator = GameAllocator(redis_client, shard_id="shard-7")
        assert allocator.shard_for("never-allocated") == "shard-7"


# ── NatsPublishingConnectionDirectory ────────────────────────────────────

class FakeNats:
    def __init__(self):
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, subject, payload):
        self.published.append((subject, payload))


class TestNatsPublishingConnectionDirectory:
    def test_register_unregister_and_liveness(self):
        hub = NatsPublishingConnectionDirectory(FakeNats(), FakeRedis(), shard_id="shard-0")
        hub.register("c1")
        assert hub.is_connected("c1")
        assert hub.all_conn_ids() == {"c1"}
        hub.unregister("c1")
        assert not hub.is_connected("c1")

    def test_associate_token_round_trip(self):
        hub = NatsPublishingConnectionDirectory(FakeNats(), FakeRedis(), shard_id="shard-0")
        hub.register("c1")
        hub.associate_token("c1", "tok-1")
        assert hub.get_conn_id_by_token("tok-1") == "c1"
        assert hub.get_token_by_conn_id("c1") == "tok-1"

    @pytest.mark.asyncio
    async def test_send_publishes_to_shard_outbound_subject(self):
        nats_client = FakeNats()
        hub = NatsPublishingConnectionDirectory(nats_client, FakeRedis(), shard_id="shard-9")
        ok = await hub.send("c1", "hello")
        assert ok is True
        assert len(nats_client.published) == 1
        subject, payload = nats_client.published[0]
        assert subject == "shard.shard-9.outbound"
        assert b'"conn_id": "c1"' in payload or b'"conn_id":"c1"' in payload

    @pytest.mark.asyncio
    async def test_broadcast_publishes_once_per_conn_id(self):
        nats_client = FakeNats()
        hub = NatsPublishingConnectionDirectory(nats_client, FakeRedis(), shard_id="shard-0")
        await hub.broadcast({"c1", "c2"}, "hi")
        assert len(nats_client.published) == 2

    def test_on_disconnect_callback_fires_on_unregister(self):
        hub = NatsPublishingConnectionDirectory(FakeNats(), FakeRedis(), shard_id="shard-0")
        seen = []
        hub.on_disconnect(lambda conn_id: seen.append(conn_id))
        hub.register("c1")
        hub.unregister("c1")
        assert seen == ["c1"]


# ── GameHandler.reconnect / get_session_by_user_id ───────────────────────

def make_player(username, user_id, conn_id, token):
    return Player(user_id=user_id, username=username, elo=1200, conn_id=conn_id, session_token=token)


def make_real_session(white, black, hub):
    return GameSession(
        game_id=str(uuid.uuid4()), white=white, black=black, hub=hub,
        user_repo=MagicMock(), game_repo=MagicMock(),
        rating_service=RatingService(load_settings()), logger=MagicMock(),
    )


class TestGameHandlerReconnect:
    def _make_handler(self):
        hub = MagicMock()
        hub.send = MagicMock(return_value=asyncio.Future())
        hub.send.return_value.set_result(True)
        return GameHandler(hub=hub, auth_service=MagicMock(spec=AuthService), logger=MagicMock()), hub

    def test_get_session_by_user_id_after_register(self):
        handler, hub = self._make_handler()
        white = make_player("alice", 1, "conn-a", "tok-a")
        black = make_player("bob", 2, "conn-b", "tok-b")
        session = make_real_session(white, black, hub)
        handler.register_session(session)

        assert handler.get_session_by_user_id(1) is session
        assert handler.get_session_by_user_id(2) is session
        assert handler.get_session_by_user_id(999) is None

    @pytest.mark.asyncio
    async def test_reconnect_repoints_conn_to_game_mapping(self):
        handler, hub = self._make_handler()
        white = make_player("alice", 1, "conn-a", "tok-a")
        black = make_player("bob", 2, "conn-b", "tok-b")
        session = make_real_session(white, black, hub)
        handler.register_session(session)

        resumed = await handler.reconnect(user_id=1, new_conn_id="conn-a-2", new_session_token="tok-a-2")
        assert resumed is True
        assert handler.get_session_by_conn("conn-a-2") is session
        assert handler.get_session_by_conn("conn-a") is None
        assert session.white.conn_id == "conn-a-2"
        assert session.white.session_token == "tok-a-2"

    @pytest.mark.asyncio
    async def test_reconnect_for_unknown_user_returns_false(self):
        handler, _ = self._make_handler()
        resumed = await handler.reconnect(user_id=42, new_conn_id="conn-x", new_session_token="tok-x")
        assert resumed is False

    @pytest.mark.asyncio
    async def test_reconnect_same_conn_id_is_a_no_op_success(self):
        handler, hub = self._make_handler()
        white = make_player("alice", 1, "conn-a", "tok-a")
        black = make_player("bob", 2, "conn-b", "tok-b")
        session = make_real_session(white, black, hub)
        handler.register_session(session)

        resumed = await handler.reconnect(user_id=1, new_conn_id="conn-a", new_session_token="tok-a")
        assert resumed is True
        assert session.white.conn_id == "conn-a"

    def test_unregister_session_clears_user_id_index(self):
        handler, hub = self._make_handler()
        white = make_player("alice", 1, "conn-a", "tok-a")
        black = make_player("bob", 2, "conn-b", "tok-b")
        session = make_real_session(white, black, hub)
        handler.register_session(session)
        handler.unregister_session(session.game_id)
        assert handler.get_session_by_user_id(1) is None
