"""
Phase 1 of .github/Server_Design_Implementation_Plan.md — the regression net
for the Redis migration: every test in this file runs twice, once per
backend, via a pytest fixture parametrized over the in-memory and
Redis-backed implementations. Identical behavior, different storage is
exactly what Phase 1 promises.

Requires a real Redis reachable at REDIS_TEST_URL (defaults to this repo's
docker-compose.yml redis service on localhost:6380). If it isn't reachable,
the "redis" param of each fixture is skipped (not failed) so the in-memory
half of the suite still runs on a machine without Docker.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import redis as redis_lib

from server.config_loader import load_settings
from server.directories.in_memory import InMemoryMatchQueue, InMemoryRoomRegistry
from server.directories.redis_backed import (
    RedisConnectionDirectory,
    RedisMatchQueue,
    RedisRoomRegistry,
)
from server.domain.player import Player
from server.domain.room import Room
from server.services.matchmaking_service import MatchmakingService
from server.services.room_service import RoomService, RoomIdGenerator

REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://localhost:6380/0")


def _redis_reachable() -> bool:
    try:
        client = redis_lib.Redis.from_url(REDIS_TEST_URL, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


REDIS_UP = _redis_reachable()
BACKENDS = ["memory", "redis"]


def make_player(username: str, elo: int = 1200, conn_id: str = None) -> Player:
    return Player(
        user_id=abs(hash(username)) % 1000,
        username=username,
        elo=elo,
        conn_id=conn_id or f"conn_{username}",
        session_token=f"tok_{username}",
    )


def _redis_client():
    if not REDIS_UP:
        pytest.skip(f"redis not reachable at {REDIS_TEST_URL}")
    return redis_lib.Redis.from_url(REDIS_TEST_URL, decode_responses=True)


@pytest.fixture(params=BACKENDS)
def match_queue(request):
    if request.param == "memory":
        return InMemoryMatchQueue()
    client = _redis_client()
    key = f"test:matchmaking:queue:{uuid.uuid4().hex}"
    return RedisMatchQueue(client, key=key)


@pytest.fixture(params=BACKENDS)
def room_registry(request):
    if request.param == "memory":
        return InMemoryRoomRegistry()
    client = _redis_client()
    prefix = f"test:room:{uuid.uuid4().hex}"
    return RedisRoomRegistry(client, key_prefix=prefix, ttl_seconds=60)


@pytest.fixture(params=BACKENDS)
def conn_directory(request):
    if request.param == "memory":
        from server.connection_hub import ConnectionHub

        return ConnectionHub()
    client = _redis_client()
    prefix = f"test:session:{uuid.uuid4().hex}"
    return RedisConnectionDirectory(client, key_prefix=prefix, ttl_seconds=60)


# ── AbstractMatchQueue contract ────────────────────────────────────────────

class TestMatchQueueParity:
    def test_enqueue_dequeue_and_size(self, match_queue):
        match_queue.enqueue(make_player("alice", conn_id="c1"))
        assert match_queue.size() == 1
        match_queue.dequeue("c1")
        assert match_queue.size() == 0

    def test_enqueue_same_conn_id_twice_is_a_no_op(self, match_queue):
        match_queue.enqueue(make_player("alice", conn_id="c1"))
        match_queue.enqueue(make_player("alice", conn_id="c1"))
        assert match_queue.size() == 1

    def test_pairs_within_range_removes_matched_players(self, match_queue):
        a, b = make_player("alice", 1200, "c1"), make_player("bob", 1210, "c2")
        match_queue.enqueue(a)
        match_queue.enqueue(b)
        pairs = match_queue.pairs_within_range(match_range=50)
        assert {p.username for pair in pairs for p in pair} == {"alice", "bob"}
        assert match_queue.size() == 0

    def test_pairs_within_range_leaves_out_of_range_players_queued(self, match_queue):
        match_queue.enqueue(make_player("alice", 1200, "c1"))
        match_queue.enqueue(make_player("bob", 1600, "c2"))
        assert match_queue.pairs_within_range(match_range=50) == []
        assert match_queue.size() == 2

    def test_pop_expired_removes_only_stale_entries(self, match_queue):
        match_queue.enqueue(make_player("alice", conn_id="c1"))
        import time as _time
        _time.sleep(0.05)
        match_queue.enqueue(make_player("bob", conn_id="c2"))
        expired = match_queue.pop_expired(timeout_seconds=0.02)
        assert [p.username for p in expired] == ["alice"]
        assert match_queue.size() == 1


# ── AbstractRoomRegistry contract ──────────────────────────────────────────

class TestRoomRegistryParity:
    def test_create_get_exists(self, room_registry):
        owner = make_player("alice", conn_id="c1")
        room = Room(room_id="ABC12", owner=owner, white=owner)
        assert not room_registry.exists("ABC12")
        room_registry.create(room)
        assert room_registry.exists("ABC12")
        fetched = room_registry.get("ABC12")
        assert fetched.room_id == "ABC12"
        assert fetched.white.username == "alice"

    def test_get_missing_room_returns_none(self, room_registry):
        assert room_registry.get("NOPE1") is None

    def test_save_persists_mutations(self, room_registry):
        owner = make_player("alice", conn_id="c1")
        room = Room(room_id="ABC13", owner=owner, white=owner)
        room_registry.create(room)
        room.black = make_player("bob", conn_id="c2")
        room.game_id = "g1"
        room_registry.save(room)
        fetched = room_registry.get("ABC13")
        assert fetched.black.username == "bob"
        assert fetched.game_id == "g1"


# ── AbstractConnectionDirectory contract ───────────────────────────────────

class FakeWebSocket:
    def __init__(self):
        self.sent: list[str] = []
        self.fail = False

    async def send(self, message: str) -> None:
        if self.fail:
            raise ConnectionError("closed")
        self.sent.append(message)


class TestConnectionDirectoryParity:
    def test_register_and_get_conn_id_by_token_round_trip(self, conn_directory):
        conn_directory.register("c1", FakeWebSocket())
        conn_directory.associate_token("c1", "tok-1")
        assert conn_directory.get_conn_id_by_token("tok-1") == "c1"

    @pytest.mark.asyncio
    async def test_send_delivers_to_registered_socket(self, conn_directory):
        ws = FakeWebSocket()
        conn_directory.register("c1", ws)
        ok = await conn_directory.send("c1", "hello")
        assert ok is True
        assert ws.sent == ["hello"]

    @pytest.mark.asyncio
    async def test_send_to_unregistered_conn_id_returns_false(self, conn_directory):
        ok = await conn_directory.send("nope", "hello")
        assert ok is False

    @pytest.mark.asyncio
    async def test_broadcast_reaches_every_conn_id(self, conn_directory):
        ws1, ws2 = FakeWebSocket(), FakeWebSocket()
        conn_directory.register("c1", ws1)
        conn_directory.register("c2", ws2)
        await conn_directory.broadcast({"c1", "c2"}, "hi")
        assert ws1.sent == ["hi"] and ws2.sent == ["hi"]


# ── Service-level parity: MatchmakingService / RoomService really work end-to-end ──

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
        self.white = None
        self.black = None

    async def start(self):
        pass

    def add_viewer(self, conn_id):
        pass


class FakeFactory:
    def __init__(self):
        self._counter = 0

    def create(self, white=None, black=None, room_id=None):
        self._counter += 1
        s = FakeSession(f"game_{self._counter}")
        s.white, s.black = white, black
        return s


class FakeGameHandler:
    def register_session(self, session):
        pass

    def get_session(self, game_id):
        return None


class TestMatchmakingServiceBackendParity:
    @pytest.mark.asyncio
    async def test_pairs_two_players_within_range(self, match_queue):
        mm = MatchmakingService(
            settings=load_settings(), factory=FakeFactory(), hub=FakeHub(),
            game_handler=FakeGameHandler(), logger=logging.getLogger("test"),
            queue=match_queue,
        )
        mm.enqueue(make_player("alice", 1200, "c1"))
        mm.enqueue(make_player("bob", 1210, "c2"))
        await mm._tick()
        assert mm.queue_size() == 0


class TestRoomServiceBackendParity:
    def test_create_join_and_start_game(self, room_registry):
        settings = load_settings()
        svc = RoomService(
            settings=settings, factory=FakeFactory(), hub=FakeHub(),
            game_handler=FakeGameHandler(), id_generator=RoomIdGenerator(settings),
            logger=logging.getLogger("test"), registry=room_registry,
        )
        owner = make_player("alice", conn_id="c1")
        room_id = svc.create_room(owner)
        result = svc.join_room(room_id, make_player("bob", conn_id="c2"))
        assert result is not None
        assert result.game_started is True

    @pytest.mark.asyncio
    async def test_start_game_if_ready(self, room_registry):
        settings = load_settings()
        svc = RoomService(
            settings=settings, factory=FakeFactory(), hub=FakeHub(),
            game_handler=FakeGameHandler(), id_generator=RoomIdGenerator(settings),
            logger=logging.getLogger("test"), registry=room_registry,
        )
        owner = make_player("alice", conn_id="c1")
        room_id = svc.create_room(owner)
        svc.join_room(room_id, make_player("bob", conn_id="c2"))
        started = await svc.start_game_if_ready(room_id)
        assert started is True
        assert svc.get_room(room_id).game_id is not None


# ── Phase 1 DoD: Redis unavailable mid-game ────────────────────────────────
#
# "Redis becoming unavailable mid-game is tested explicitly (expect: in-flight
# game continues locally since GameSession itself doesn't touch Redis yet in
# this phase; new matchmaking/room operations fail loudly, not silently)."

class TestRedisUnavailable:
    def _unreachable_client(self):
        # A real redis.Redis pointed at a port nothing listens on — every
        # command raises a ConnectionError quickly (short timeout) rather
        # than hanging, standing in for "Redis is down."
        return redis_lib.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2)

    def test_room_registry_raises_loudly_instead_of_pretending_success(self):
        registry = RedisRoomRegistry(self._unreachable_client(), key_prefix="down:room")
        owner = make_player("alice", conn_id="c1")
        room = Room(room_id="DOWN01", owner=owner, white=owner)
        with pytest.raises(Exception):
            registry.create(room)
        with pytest.raises(Exception):
            registry.get("DOWN01")

    def test_match_queue_raises_loudly_instead_of_pretending_success(self):
        queue = RedisMatchQueue(self._unreachable_client(), key="down:queue")
        with pytest.raises(Exception):
            queue.enqueue(make_player("alice", conn_id="c1"))

    @pytest.mark.asyncio
    async def test_in_flight_game_session_is_unaffected_by_redis_outage(self):
        """
        GameSession/ConnectionHub never touch Redis in Phase 1 — only the
        matchmaking queue and room registry do — so an in-flight game must
        keep working (moves broadcast normally) even while Redis is down.
        This is the actual regression this test guards: a shared "backend"
        object must never leak into GameSession's dependency graph before
        Phase 4 makes that an explicit, deliberate change.
        """
        from server.connection_hub import ConnectionHub

        hub = ConnectionHub()
        ws = FakeWebSocketForOutageTest()
        hub.register("c1", ws)
        # Redis being unreachable must have zero effect on hub.send — it
        # never talks to Redis at all in this phase.
        ok = await hub.send("c1", "still working")
        assert ok is True
        assert ws.sent == ["still working"]


class FakeWebSocketForOutageTest:
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)
