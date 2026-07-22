"""
Phase 4 unit tests: GameSession — move handling, end_game, rating update.

Uses a fake hub (no real sockets) so tests run without a network.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from server.config_loader import load_settings
from server.domain.enums import GameResult, EndReason
from server.domain.player import Player
from server.repositories.base_repository import (
    AbstractUserRepository, AbstractGameRepository, UserRecord,
)
from server.services.game_session import GameSession
from server.services.game_session_factory import GameSessionFactory
from server.services.rating_service import RatingService


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeHub:
    def __init__(self):
        self.sent: dict[str, list[str]] = {}
        self._tokens: dict[str, str] = {}   # token → conn_id

    def associate_token(self, conn_id: str, token: str) -> None:
        self._tokens[token] = conn_id

    def all_conn_ids(self):
        return set(self.sent.keys())

    async def send(self, conn_id: str, msg: str) -> bool:
        self.sent.setdefault(conn_id, []).append(msg)
        return True

    async def broadcast(self, conn_ids, msg: str) -> None:
        for c in conn_ids:
            await self.send(c, msg)

    async def broadcast_to_tokens(self, tokens, msg: str) -> None:
        for t in tokens:
            conn_id = self._tokens.get(t)
            if conn_id:
                await self.send(conn_id, msg)


class FakeUserRepo(AbstractUserRepository):
    def __init__(self):
        self._users: dict[int, UserRecord] = {}
        self._by_username: dict[str, int] = {}
        self._counter = 1
        self.elo_updates: list[tuple[int, int]] = []

    def create(self, username, password_hash, starting_elo):
        uid = self._counter
        self._counter += 1
        rec = UserRecord(uid, username, password_hash, starting_elo, "now", None)
        self._users[uid] = rec
        self._by_username[username] = uid
        return rec

    def get_by_username(self, username):
        uid = self._by_username.get(username)
        return self._users.get(uid) if uid else None

    def get_by_id(self, user_id):
        return self._users.get(user_id)

    def update_elo(self, user_id, new_elo):
        self.elo_updates.append((user_id, new_elo))
        if user_id in self._users:
            old = self._users[user_id]
            self._users[user_id] = UserRecord(
                old.id, old.username, old.password_hash, new_elo, old.created_at, old.last_login_at
            )

    def update_last_login(self, user_id):
        pass


class FakeGameRepo(AbstractGameRepository):
    def __init__(self):
        self.records: list[dict] = []

    def record_game(self, **kwargs) -> int:
        self.records.append(kwargs)
        return len(self.records)

    def get_by_id(self, game_id):
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_session(hub=None, user_repo=None, game_repo=None):
    settings = load_settings()
    hub = hub or FakeHub()
    user_repo = user_repo or FakeUserRepo()
    game_repo = game_repo or FakeGameRepo()
    rating = RatingService(settings)
    white = Player(1, "alice", 1200, "conn_white", "tok_white")
    black = Player(2, "bob", 1200, "conn_black", "tok_black")
    # Register tokens so broadcast_to_tokens can resolve them
    hub.associate_token("conn_white", "tok_white")
    hub.associate_token("conn_black", "tok_black")
    return GameSession(
        game_id="game123",
        white=white,
        black=black,
        hub=hub,
        user_repo=user_repo,
        game_repo=game_repo,
        rating_service=rating,
        logger=logging.getLogger("test"),
        disconnect_grace_seconds=2,
        countdown_tick_seconds=0.1,
    ), hub, user_repo, game_repo


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGameSession:
    @pytest.mark.asyncio
    async def test_start_sends_game_start(self):
        session, hub, _, _ = make_session()
        await session.start()
        assert "conn_white" in hub.sent
        assert "conn_black" in hub.sent
        # Verify GAME_START type in sent messages
        import json
        for conn in ("conn_white", "conn_black"):
            msgs = hub.sent[conn]
            assert any(json.loads(m)["type"] == "GAME_START" for m in msgs)

    @pytest.mark.asyncio
    async def test_apply_valid_move(self):
        session, hub, _, _ = make_session()
        # White pawn at row 6 col 4 → row 4 col 4 (two-square advance)
        result = await session.apply_move("conn_white", 6, 4, 4, 4)
        assert result.accepted

    @pytest.mark.asyncio
    async def test_apply_illegal_move_rejected(self):
        session, hub, _, _ = make_session()
        # Pawn cannot move backward
        result = await session.apply_move("conn_white", 6, 4, 7, 4)
        assert not result.accepted

    @pytest.mark.asyncio
    async def test_move_by_non_player_rejected(self):
        session, hub, _, _ = make_session()
        result = await session.apply_move("conn_viewer", 6, 4, 4, 4)
        assert not result.accepted

    @pytest.mark.asyncio
    async def test_end_game_updates_elo_exactly_once(self):
        session, _, user_repo, _ = make_session()
        await session.end_game(GameResult.WHITE_WINS, EndReason.RESIGN)
        # Two elo updates: one per player
        assert len(user_repo.elo_updates) == 2

    @pytest.mark.asyncio
    async def test_end_game_persists_record(self):
        session, _, _, game_repo = make_session()
        await session.end_game(GameResult.WHITE_WINS, EndReason.RESIGN)
        assert len(game_repo.records) == 1
        rec = game_repo.records[0]
        assert rec["result"] == "white"
        assert rec["end_reason"] == "resign"

    @pytest.mark.asyncio
    async def test_end_game_not_called_twice(self):
        session, _, user_repo, game_repo = make_session()
        await session.end_game(GameResult.WHITE_WINS, EndReason.RESIGN)
        await session.end_game(GameResult.BLACK_WINS, EndReason.RESIGN)
        # Second call should be ignored
        assert len(game_repo.records) == 1
        assert len(user_repo.elo_updates) == 2

    @pytest.mark.asyncio
    async def test_end_game_broadcasts_game_end(self):
        session, hub, _, _ = make_session()
        await session.end_game(GameResult.DRAW, EndReason.DRAW_AGREEMENT)
        import json
        for conn in ("conn_white", "conn_black"):
            msgs = hub.sent.get(conn, [])
            assert any(json.loads(m)["type"] == "GAME_END" for m in msgs)

    @pytest.mark.asyncio
    async def test_viewers_receive_move_broadcast(self):
        session, hub, _, _ = make_session()
        session.add_viewer("conn_viewer")
        await session.apply_move("conn_white", 6, 4, 4, 4)
        import json
        msgs = hub.sent.get("conn_viewer", [])
        assert any(json.loads(m)["type"] == "MOVE_BROADCAST" for m in msgs)

    @pytest.mark.asyncio
    async def test_viewers_cannot_move(self):
        session, _, _, _ = make_session()
        session.add_viewer("conn_viewer")
        result = await session.apply_move("conn_viewer", 6, 4, 4, 4)
        assert not result.accepted

    @pytest.mark.asyncio
    async def test_get_state_does_not_expose_internals(self):
        session, _, _, _ = make_session()
        state = session.get_state()
        assert hasattr(state, "grid")
        assert hasattr(state, "game_over")
        # Should not be the raw engine object
        assert not hasattr(state, "_board")

    @pytest.mark.asyncio
    async def test_elo_updated_correctly_on_white_win(self):
        session, _, user_repo, _ = make_session()
        await session.end_game(GameResult.WHITE_WINS, EndReason.CHECKMATE)
        # White (id=1) should get 1216, Black (id=2) should get 1184
        updates = {uid: elo for uid, elo in user_repo.elo_updates}
        assert updates[1] == 1216
        assert updates[2] == 1184


# ── GameSessionFactory ────────────────────────────────────────────────────────

class TestGameSessionFactory:
    def test_creates_game_session(self):
        settings = load_settings()
        hub = FakeHub()
        user_repo = FakeUserRepo()
        game_repo = FakeGameRepo()
        rating = RatingService(settings)
        factory = GameSessionFactory(
            hub=hub, user_repo=user_repo, game_repo=game_repo,
            rating_service=rating, settings=settings,
            logger=logging.getLogger("test"),
        )
        white = Player(1, "alice", 1200, "c1", "t1")
        black = Player(2, "bob", 1200, "c2", "t2")
        session = factory.create(white, black)
        assert session.game_id != ""
        assert session.white.username == "alice"
        assert session.black.username == "bob"

    def test_two_sessions_have_different_ids(self):
        settings = load_settings()
        hub = FakeHub()
        user_repo = FakeUserRepo()
        game_repo = FakeGameRepo()
        rating = RatingService(settings)
        factory = GameSessionFactory(
            hub=hub, user_repo=user_repo, game_repo=game_repo,
            rating_service=rating, settings=settings,
            logger=logging.getLogger("test"),
        )
        white = Player(1, "alice", 1200, "c1", "t1")
        black = Player(2, "bob", 1200, "c2", "t2")
        s1 = factory.create(white, black)
        s2 = factory.create(white, black)
        assert s1.game_id != s2.game_id
