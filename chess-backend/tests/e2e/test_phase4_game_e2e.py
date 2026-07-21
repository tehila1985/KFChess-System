"""
Phase 4 e2e test: two clients play a game to resign, verify rating update.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid

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
from server.repositories.user_repository import UserRepository
from server.repositories.game_repository import GameRepository
from server.db.database import get_connection
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope

TEST_PORT = 18767


async def _run_game_server(stop_event: asyncio.Event, ready_event: asyncio.Event,
                            shared: dict):
    settings = load_settings()
    raw_logger = logging.getLogger("chess.test.game")
    conn = get_connection(":memory:")
    user_repo = UserRepository(conn)
    game_repo = GameRepository(conn)
    auth_svc = AuthService(repo=user_repo, settings=settings, logger=raw_logger)
    rating_svc = RatingService(settings)
    hub = ConnectionHub(logger=raw_logger)
    game_handler = GameHandler(hub=hub, auth_service=auth_svc, logger=raw_logger)
    factory = GameSessionFactory(
        hub=hub, user_repo=user_repo, game_repo=game_repo,
        rating_service=rating_svc, settings=settings, logger=raw_logger,
    )
    router = MessageRouter(hub=hub, logger=raw_logger)
    auth_handler = AuthHandler(auth_service=auth_svc, hub=hub, logger=raw_logger)

    router.register(MessageType.PING, make_ping_handler(hub, raw_logger))
    router.register(MessageType.LOGIN, auth_handler.make_login_handler())
    router.register(MessageType.REGISTER, auth_handler.make_register_handler())
    router.register(MessageType.MOVE, game_handler.make_move_handler())
    router.register(MessageType.RESIGN, game_handler.make_resign_handler())

    shared["hub"] = hub
    shared["factory"] = factory
    shared["game_handler"] = game_handler
    shared["auth_svc"] = auth_svc
    shared["user_repo"] = user_repo

    async def handler(websocket):
        conn_id = str(uuid.uuid4())
        hub.register(conn_id, websocket)
        try:
            async for raw in websocket:
                await router.route(conn_id, raw)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            hub.unregister(conn_id)

    async with websockets.serve(handler, "127.0.0.1", TEST_PORT):
        ready_event.set()
        await stop_event.wait()


@pytest.mark.asyncio
async def test_full_game_resign():
    stop_event = asyncio.Event()
    ready_event = asyncio.Event()
    shared = {}
    srv = asyncio.create_task(_run_game_server(stop_event, ready_event, shared))
    await asyncio.wait_for(ready_event.wait(), 5.0)

    try:
        # Two clients connect, register, then we create a game session directly
        async with (
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws1,
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws2,
        ):
            # Register alice and bob
            for ws, uname in ((ws1, "alice_g"), (ws2, "bob_g")):
                env = Envelope(
                    type=MessageType.REGISTER,
                    payload={"username": uname, "password": "password123"},
                )
                await ws.send(env.to_json())
                await asyncio.wait_for(ws.recv(), 3.0)

            # Login both
            alice_token, bob_token = None, None
            for ws, uname, attr in ((ws1, "alice_g", "alice_token"),
                                     (ws2, "bob_g", "bob_token")):
                env = Envelope(
                    type=MessageType.LOGIN,
                    payload={"username": uname, "password": "password123"},
                )
                await ws.send(env.to_json())
                resp = Envelope.from_json(await asyncio.wait_for(ws.recv(), 3.0))
                assert resp.type == MessageType.LOGIN_OK
                if uname == "alice_g":
                    alice_token = resp.payload["session_token"]
                else:
                    bob_token = resp.payload["session_token"]

            hub = shared["hub"]
            factory = shared["factory"]
            game_handler = shared["game_handler"]
            user_repo = shared["user_repo"]

            # Find conn_ids for alice and bob by token
            alice_conn = hub.get_conn_id_by_token(alice_token)
            bob_conn = hub.get_conn_id_by_token(bob_token)
            assert alice_conn is not None
            assert bob_conn is not None

            alice_user = user_repo.get_by_username("alice_g")
            bob_user = user_repo.get_by_username("bob_g")

            white_player = Player(alice_user.id, "alice_g", alice_user.elo, alice_conn, alice_token)
            black_player = Player(bob_user.id, "bob_g", bob_user.elo, bob_conn, bob_token)

            session = factory.create(white_player, black_player)
            game_handler.register_session(session)
            await session.start()

            # Both should receive GAME_START
            resp1 = Envelope.from_json(await asyncio.wait_for(ws1.recv(), 3.0))
            resp2 = Envelope.from_json(await asyncio.wait_for(ws2.recv(), 3.0))
            assert resp1.type == MessageType.GAME_START
            assert resp2.type == MessageType.GAME_START

            # Alice (white) resigns
            resign_env = Envelope(
                type=MessageType.RESIGN,
                payload={"session_token": alice_token},
            )
            await ws1.send(resign_env.to_json())

            # Both should receive GAME_END
            msgs1 = []
            msgs2 = []
            for _ in range(3):
                try:
                    raw = await asyncio.wait_for(ws1.recv(), 1.0)
                    msgs1.append(Envelope.from_json(raw))
                except asyncio.TimeoutError:
                    break
            for _ in range(3):
                try:
                    raw = await asyncio.wait_for(ws2.recv(), 1.0)
                    msgs2.append(Envelope.from_json(raw))
                except asyncio.TimeoutError:
                    break

            end1 = next((m for m in msgs1 if m.type == MessageType.GAME_END), None)
            end2 = next((m for m in msgs2 if m.type == MessageType.GAME_END), None)
            assert end1 is not None, "Alice should receive GAME_END"
            assert end2 is not None, "Bob should receive GAME_END"
            assert end1.payload["result"] == "black"
            assert end1.payload["reason"] == "resign"

            # Verify ELO was updated in DB
            alice_after = user_repo.get_by_username("alice_g")
            bob_after = user_repo.get_by_username("bob_g")
            assert alice_after.elo == 1184   # lost
            assert bob_after.elo == 1216     # won

    finally:
        stop_event.set()
        await srv
