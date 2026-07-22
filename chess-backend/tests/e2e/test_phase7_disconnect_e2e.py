"""
Phase 7 e2e tests — disconnect handling.

Strategy: test the disconnect *mechanism* (monitor fires → end_game →
GAME_END broadcast) without relying on a real countdown timer in a test
server. The countdown logic is already covered by 13 unit tests. Here we
focus on the observable outcomes:
  1. Opponent receives OPPONENT_DISCONNECTED when a player closes.
  2. end_game correctly broadcasts GAME_END (tested via direct session call).
  3. Reconnecting within the grace period cancels the monitor.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import websockets

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from server.config_loader import load_settings
from server.connection_hub import ConnectionHub
from server.message_router import MessageRouter
from server.handlers.system_handler import make_ping_handler
from server.handlers.auth_handler import AuthHandler
from server.handlers.game_handler import GameHandler
from server.services.auth_service import AuthService
from server.services.rating_service import RatingService
from server.services.game_session_factory import GameSessionFactory
from server.services.game_session import GameSession
from server.domain.player import Player
from server.domain.enums import GameResult, EndReason
from server.repositories.user_repository import UserRepository
from server.repositories.game_repository import GameRepository
from server.db.database import get_connection
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope

TEST_PORT = 18770


# ── Shared test-server infrastructure ─────────────────────────────────────────

async def _run_server(stop_event, ready_event, shared, port=TEST_PORT):
    settings = load_settings()
    logger = logging.getLogger("chess.test.disconnect")
    db_conn = get_connection(":memory:")
    user_repo = UserRepository(db_conn)
    game_repo = GameRepository(db_conn)
    auth_svc = AuthService(repo=user_repo, settings=settings, logger=logger)
    rating_svc = RatingService(settings)
    hub = ConnectionHub(logger=logger)
    game_handler = GameHandler(hub=hub, auth_service=auth_svc, logger=logger)
    factory = GameSessionFactory(
        hub=hub, user_repo=user_repo, game_repo=game_repo,
        rating_service=rating_svc, settings=settings, logger=logger,
    )
    router = MessageRouter(hub=hub, logger=logger)
    auth_handler = AuthHandler(auth_service=auth_svc, hub=hub, logger=logger)

    router.register(MessageType.PING, make_ping_handler(hub, logger))
    router.register(MessageType.LOGIN, auth_handler.make_login_handler())
    router.register(MessageType.REGISTER, auth_handler.make_register_handler())
    router.register(MessageType.RESIGN, game_handler.make_resign_handler())

    shared.update(dict(hub=hub, factory=factory, game_handler=game_handler,
                       user_repo=user_repo, game_repo=game_repo,
                       auth_svc=auth_svc))

    async def handler(websocket):
        conn_id = str(uuid.uuid4())
        hub.register(conn_id, websocket)
        try:
            async for raw in websocket:
                await router.route(conn_id, raw)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            session = game_handler.get_session_by_conn(conn_id)
            hub.unregister(conn_id)
            if session is not None:
                asyncio.ensure_future(session.handle_disconnect(conn_id))

    async with websockets.serve(handler, "127.0.0.1", port):
        ready_event.set()
        await stop_event.wait()


async def _register_login(ws, username, password="Password1!"):
    await ws.send(Envelope(type=MessageType.REGISTER,
                           payload={"username": username, "password": password}).to_json())
    await asyncio.wait_for(ws.recv(), 3.0)
    await ws.send(Envelope(type=MessageType.LOGIN,
                           payload={"username": username, "password": password}).to_json())
    resp = Envelope.from_json(await asyncio.wait_for(ws.recv(), 3.0))
    assert resp.type == MessageType.LOGIN_OK
    return resp.payload["session_token"]


async def _drain(ws, count=1, timeout=2.0):
    msgs = []
    for _ in range(count):
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout)
            msgs.append(json.loads(raw))
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            break
    return msgs


# ── Test 1: opponent receives OPPONENT_DISCONNECTED when player closes ─────────

@pytest.mark.asyncio
async def test_opponent_sees_disconnect_notification():
    """
    When Alice closes her connection during a game, Bob immediately
    receives an OPPONENT_DISCONNECTED message.
    """
    stop_event = asyncio.Event()
    ready_event = asyncio.Event()
    shared = {}
    srv = asyncio.create_task(_run_server(stop_event, ready_event, shared))
    await asyncio.wait_for(ready_event.wait(), 5.0)

    try:
        async with (
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws1,
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws2,
        ):
            t1 = await _register_login(ws1, "notif_alice")
            t2 = await _register_login(ws2, "notif_bob")

            hub = shared["hub"]
            factory = shared["factory"]
            game_handler = shared["game_handler"]
            user_repo = shared["user_repo"]

            c1 = hub.get_conn_id_by_token(t1)
            c2 = hub.get_conn_id_by_token(t2)
            u1 = user_repo.get_by_username("notif_alice")
            u2 = user_repo.get_by_username("notif_bob")

            white = Player(u1.id, "notif_alice", u1.elo, c1, t1)
            black = Player(u2.id, "notif_bob",   u2.elo, c2, t2)
            session = factory.create(white, black)
            game_handler.register_session(session)
            await session.start()
            await _drain(ws1, 1)  # GAME_START
            await _drain(ws2, 1)  # GAME_START

            # Alice closes
            await ws1.close()

            # Bob should receive OPPONENT_DISCONNECTED quickly
            msgs = await _drain(ws2, count=3, timeout=3.0)
            types = [m.get("type") for m in msgs]
            assert "OPPONENT_DISCONNECTED" in types, \
                f"Bob must receive OPPONENT_DISCONNECTED. Got: {types}"
    finally:
        stop_event.set()
        await srv


# ── Test 2: end_game broadcasts GAME_END (unit-style, no countdown wait) ──────

@pytest.mark.asyncio
async def test_end_game_sends_game_end_to_both_players():
    """
    Calling session.end_game() directly results in both players receiving
    GAME_END. This verifies the broadcast path without timing out on a
    real countdown.
    """
    stop_event = asyncio.Event()
    ready_event = asyncio.Event()
    shared = {}
    srv = asyncio.create_task(_run_server(stop_event, ready_event, shared))
    await asyncio.wait_for(ready_event.wait(), 5.0)

    try:
        async with (
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws1,
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws2,
        ):
            t1 = await _register_login(ws1, "end_alice")
            t2 = await _register_login(ws2, "end_bob")

            hub = shared["hub"]
            factory = shared["factory"]
            game_handler = shared["game_handler"]
            user_repo = shared["user_repo"]

            c1 = hub.get_conn_id_by_token(t1)
            c2 = hub.get_conn_id_by_token(t2)
            u1 = user_repo.get_by_username("end_alice")
            u2 = user_repo.get_by_username("end_bob")

            white = Player(u1.id, "end_alice", u1.elo, c1, t1)
            black = Player(u2.id, "end_bob",   u2.elo, c2, t2)
            session = factory.create(white, black)
            game_handler.register_session(session)
            await session.start()
            await _drain(ws1, 1)  # GAME_START
            await _drain(ws2, 1)  # GAME_START

            # Trigger end_game directly (simulates auto-resign outcome)
            await session.end_game(GameResult.BLACK_WINS, EndReason.DISCONNECT_TIMEOUT)

            # Both players should receive GAME_END
            msgs1 = await _drain(ws1, count=3, timeout=2.0)
            msgs2 = await _drain(ws2, count=3, timeout=2.0)

            types1 = [m.get("type") for m in msgs1]
            types2 = [m.get("type") for m in msgs2]

            assert "GAME_END" in types1, f"Alice must receive GAME_END. Got: {types1}"
            assert "GAME_END" in types2, f"Bob must receive GAME_END. Got: {types2}"

            end = next(m for m in msgs2 if m.get("type") == "GAME_END")
            assert end["payload"]["result"] == "black"
            assert end["payload"]["reason"] == "disconnect_timeout"

            # ELO updated in DB
            assert user_repo.get_by_username("end_alice").elo == 1184
            assert user_repo.get_by_username("end_bob").elo == 1216
    finally:
        stop_event.set()
        await srv


# ── Test 3: reconnect cancels the countdown ────────────────────────────────────

@pytest.mark.asyncio
async def test_reconnect_cancels_countdown():
    """
    If the disconnected player reconnects and the session's handle_reconnect
    is called within the grace period, no GAME_END is sent to the opponent.
    """
    stop_event = asyncio.Event()
    ready_event = asyncio.Event()
    shared = {}
    srv = asyncio.create_task(_run_server(stop_event, ready_event, shared))
    await asyncio.wait_for(ready_event.wait(), 5.0)

    try:
        async with (
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws1,
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws2,
        ):
            t1 = await _register_login(ws1, "recon_alice")
            t2 = await _register_login(ws2, "recon_bob")

            hub = shared["hub"]
            factory = shared["factory"]
            game_handler = shared["game_handler"]
            user_repo = shared["user_repo"]

            c1 = hub.get_conn_id_by_token(t1)
            c2 = hub.get_conn_id_by_token(t2)
            u1 = user_repo.get_by_username("recon_alice")
            u2 = user_repo.get_by_username("recon_bob")

            white = Player(u1.id, "recon_alice", u1.elo, c1, t1)
            black = Player(u2.id, "recon_bob",   u2.elo, c2, t2)
            session = factory.create(white, black)
            game_handler.register_session(session)
            await session.start()
            await _drain(ws1, 1)
            await _drain(ws2, 1)

            old_conn = white.conn_id

            # Alice disconnects
            await ws1.close()
            await asyncio.sleep(0.1)  # let disconnect propagate

            # Cancel the monitor immediately (simulates reconnect within grace)
            await session.handle_reconnect(old_conn, "new-placeholder")

            # Wait to confirm no GAME_END arrives for Bob
            msgs = await _drain(ws2, count=5, timeout=1.5)
            types = [m.get("type") for m in msgs]

            assert "GAME_END" not in types, \
                f"No GAME_END expected after reconnect. Got: {types}"
    finally:
        stop_event.set()
        await srv
