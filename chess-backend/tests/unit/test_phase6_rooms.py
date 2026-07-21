"""
Phase 6 unit tests: RoomIdGenerator, RoomService — create/join/role assignment.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from server.config_loader import load_settings
from server.domain.enums import RoomRole
from server.domain.player import Player
from server.services.room_service import RoomService, RoomIdGenerator, JoinResult


# ── Fakes (reuse from phase 4 pattern) ───────────────────────────────────────

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
    def __init__(self, game_id="gX"):
        self.game_id = game_id
        self.white = None
        self.black = None
        self.viewers_added = []
        self.started = False

    def add_viewer(self, conn_id):
        self.viewers_added.append(conn_id)

    async def start(self):
        self.started = True


class FakeFactory:
    def __init__(self):
        self.sessions: list[FakeSession] = []
        self._counter = 0

    def create(self, white, black, room_id=None):
        self._counter += 1
        s = FakeSession(f"g{self._counter}")
        s.white = white
        s.black = black
        self.sessions.append(s)
        return s


class FakeGameHandler:
    def __init__(self):
        self.sessions: list = []

    def register_session(self, session):
        self.sessions.append(session)


def make_player(username: str, conn_id: str = None) -> Player:
    return Player(
        user_id=abs(hash(username)) % 1000,
        username=username,
        elo=1200,
        conn_id=conn_id or f"conn_{username}",
        session_token=f"tok_{username}",
    )


def make_room_service():
    settings = load_settings()
    hub = FakeHub()
    factory = FakeFactory()
    game_handler = FakeGameHandler()
    id_gen = RoomIdGenerator(settings)
    svc = RoomService(
        settings=settings,
        factory=factory,
        hub=hub,
        game_handler=game_handler,
        id_generator=id_gen,
        logger=logging.getLogger("test"),
    )
    return svc, factory, hub, game_handler


# ── RoomIdGenerator ───────────────────────────────────────────────────────────

class TestRoomIdGenerator:
    def test_id_length(self):
        settings = load_settings()
        gen = RoomIdGenerator(settings)
        rid = gen.generate()
        assert len(rid) == settings.room.id_length

    def test_only_allowed_characters(self):
        settings = load_settings()
        gen = RoomIdGenerator(settings)
        for _ in range(50):
            rid = gen.generate()
            for ch in rid:
                assert ch in settings.room.id_alphabet

    def test_generates_unique_ids(self):
        settings = load_settings()
        gen = RoomIdGenerator(settings)
        ids = {gen.generate() for _ in range(100)}
        # Very high probability all 100 are unique given alphabet size
        assert len(ids) > 90


# ── RoomService ───────────────────────────────────────────────────────────────

class TestRoomService:
    def test_create_room_returns_id(self):
        svc, *_ = make_room_service()
        owner = make_player("alice")
        room_id = svc.create_room(owner)
        assert len(room_id) == 6

    def test_owner_is_white(self):
        svc, *_ = make_room_service()
        owner = make_player("alice")
        room_id = svc.create_room(owner)
        room = svc.get_room(room_id)
        assert room.white.username == "alice"
        assert room.black is None

    def test_second_player_is_black(self):
        svc, factory, *_ = make_room_service()
        owner = make_player("alice", "c1")
        room_id = svc.create_room(owner)
        bob = make_player("bob", "c2")
        result = svc.join_room(room_id, bob)
        assert result is not None
        assert result.role == RoomRole.BLACK
        room = svc.get_room(room_id)
        assert room.black.username == "bob"

    def test_third_player_is_viewer(self):
        svc, *_ = make_room_service()
        owner = make_player("alice", "c1")
        room_id = svc.create_room(owner)
        svc.join_room(room_id, make_player("bob", "c2"))
        charlie = make_player("charlie", "c3")
        result = svc.join_room(room_id, charlie)
        assert result.role == RoomRole.VIEWER

    def test_join_nonexistent_room_returns_none(self):
        svc, *_ = make_room_service()
        result = svc.join_room("BADROOM", make_player("alice"))
        assert result is None

    def test_game_starts_when_second_player_joins(self):
        svc, *_ = make_room_service()
        result = svc.join_room("BADROOM", make_player("alice"))
        assert result is None

    @pytest.mark.asyncio
    async def test_game_started_after_second_join(self):
        svc, factory, _, game_handler = make_room_service()
        owner = make_player("alice", "c1")
        room_id = svc.create_room(owner)
        bob = make_player("bob", "c2")
        result = svc.join_room(room_id, bob)
        assert result.game_started
        await svc.start_game_if_ready(room_id)
        assert len(factory.sessions) == 1
        assert factory.sessions[0].started

    @pytest.mark.asyncio
    async def test_viewers_added_to_session(self):
        svc, factory, _, game_handler = make_room_service()
        owner = make_player("alice", "c1")
        room_id = svc.create_room(owner)
        svc.join_room(room_id, make_player("bob", "c2"))
        # Add viewer before game starts
        charlie = make_player("charlie", "c3")
        svc.join_room(room_id, charlie)
        await svc.start_game_if_ready(room_id)
        session = factory.sessions[0]
        assert "c3" in session.viewers_added

    @pytest.mark.asyncio
    async def test_session_registered_with_game_handler(self):
        svc, factory, _, game_handler = make_room_service()
        owner = make_player("alice", "c1")
        room_id = svc.create_room(owner)
        svc.join_room(room_id, make_player("bob", "c2"))
        await svc.start_game_if_ready(room_id)
        assert len(game_handler.sessions) == 1

    @pytest.mark.asyncio
    async def test_game_not_started_with_only_one_player(self):
        svc, factory, _, _ = make_room_service()
        owner = make_player("alice", "c1")
        room_id = svc.create_room(owner)
        result = await svc.start_game_if_ready(room_id)
        assert result is False
        assert len(factory.sessions) == 0
