"""
Phase 6 e2e test: create room, two players join (one becomes viewer), game starts.
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
from server.handlers.room_handler import RoomHandler
from server.services.auth_service import AuthService
from server.services.rating_service import RatingService
from server.services.room_service import RoomService, RoomIdGenerator
from server.services.game_session_factory import GameSessionFactory
from server.repositories.user_repository import UserRepository
from server.repositories.game_repository import GameRepository
from server.db.database import get_connection
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope

TEST_PORT = 18769


async def _run_room_server(stop_event: asyncio.Event, ready_event: asyncio.Event):
    settings = load_settings()
    raw_logger = logging.getLogger("chess.test.room")
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
    id_gen = RoomIdGenerator(settings)
    room_svc = RoomService(
        settings=settings, factory=factory, hub=hub,
        game_handler=game_handler, id_generator=id_gen, logger=raw_logger,
    )
    router = MessageRouter(hub=hub, logger=raw_logger)
    auth_handler = AuthHandler(auth_service=auth_svc, hub=hub, logger=raw_logger)
    room_handler = RoomHandler(
        room_service=room_svc, auth_service=auth_svc, user_repo=user_repo,
        hub=hub, logger=raw_logger,
    )

    router.register(MessageType.PING, make_ping_handler(hub, raw_logger))
    router.register(MessageType.LOGIN, auth_handler.make_login_handler())
    router.register(MessageType.REGISTER, auth_handler.make_register_handler())
    router.register(MessageType.ROOM_CREATE, room_handler.make_room_create_handler())
    router.register(MessageType.ROOM_JOIN, room_handler.make_room_join_handler())
    router.register(MessageType.MOVE, game_handler.make_move_handler())
    router.register(MessageType.RESIGN, game_handler.make_resign_handler())

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


async def _register_and_login(ws, username):
    env = Envelope(
        type=MessageType.REGISTER,
        payload={"username": username, "password": "password123"},
    )
    await ws.send(env.to_json())
    await asyncio.wait_for(ws.recv(), 3.0)
    env = Envelope(
        type=MessageType.LOGIN,
        payload={"username": username, "password": "password123"},
    )
    await ws.send(env.to_json())
    resp = Envelope.from_json(await asyncio.wait_for(ws.recv(), 3.0))
    assert resp.type == MessageType.LOGIN_OK
    return resp.payload["session_token"]


@pytest.mark.asyncio
async def test_room_create_join_game_starts():
    stop_event = asyncio.Event()
    ready_event = asyncio.Event()
    srv = asyncio.create_task(_run_room_server(stop_event, ready_event))
    await asyncio.wait_for(ready_event.wait(), 5.0)

    try:
        async with (
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws1,
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws2,
        ):
            tok1 = await _register_and_login(ws1, "room_alice")
            tok2 = await _register_and_login(ws2, "room_bob")

            # Alice creates room
            create_env = Envelope(
                type=MessageType.ROOM_CREATE,
                payload={"session_token": tok1},
            )
            await ws1.send(create_env.to_json())
            r = Envelope.from_json(await asyncio.wait_for(ws1.recv(), 3.0))
            assert r.type == MessageType.ROOM_CREATED
            room_id = r.payload["room_id"]
            assert len(room_id) == 6

            # Bob joins room
            join_env = Envelope(
                type=MessageType.ROOM_JOIN,
                payload={"session_token": tok2, "room_id": room_id},
            )
            await ws2.send(join_env.to_json())
            r2 = Envelope.from_json(await asyncio.wait_for(ws2.recv(), 3.0))
            assert r2.type == MessageType.ROOM_ROLE_ASSIGNED
            assert r2.payload["role"] == "black"

            # Both should receive GAME_START
            gs1 = Envelope.from_json(await asyncio.wait_for(ws1.recv(), 3.0))
            gs2 = Envelope.from_json(await asyncio.wait_for(ws2.recv(), 3.0))
            assert gs1.type == MessageType.GAME_START
            assert gs2.type == MessageType.GAME_START
            assert gs1.payload["room_id"] == room_id
    finally:
        stop_event.set()
        await srv


@pytest.mark.asyncio
async def test_room_three_clients_third_is_viewer():
    stop_event = asyncio.Event()
    ready_event = asyncio.Event()
    srv = asyncio.create_task(_run_room_server(stop_event, ready_event))
    await asyncio.wait_for(ready_event.wait(), 5.0)

    try:
        async with (
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws1,
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws2,
            websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws3,
        ):
            tok1 = await _register_and_login(ws1, "room_x_alice")
            tok2 = await _register_and_login(ws2, "room_x_bob")
            tok3 = await _register_and_login(ws3, "room_x_charlie")

            # Alice creates
            create_env = Envelope(
                type=MessageType.ROOM_CREATE,
                payload={"session_token": tok1},
            )
            await ws1.send(create_env.to_json())
            r = Envelope.from_json(await asyncio.wait_for(ws1.recv(), 3.0))
            room_id = r.payload["room_id"]

            # Bob joins (→ black)
            await ws2.send(Envelope(
                type=MessageType.ROOM_JOIN,
                payload={"session_token": tok2, "room_id": room_id},
            ).to_json())
            r2 = Envelope.from_json(await asyncio.wait_for(ws2.recv(), 3.0))
            assert r2.payload["role"] == "black"

            # Drain GAME_START for alice and bob
            await asyncio.wait_for(ws1.recv(), 3.0)
            await asyncio.wait_for(ws2.recv(), 3.0)

            # Charlie joins (→ viewer)
            await ws3.send(Envelope(
                type=MessageType.ROOM_JOIN,
                payload={"session_token": tok3, "room_id": room_id},
            ).to_json())
            r3 = Envelope.from_json(await asyncio.wait_for(ws3.recv(), 3.0))
            assert r3.payload["role"] == "viewer"

    finally:
        stop_event.set()
        await srv


@pytest.mark.asyncio
async def test_bad_room_id_returns_error():
    stop_event = asyncio.Event()
    ready_event = asyncio.Event()
    srv = asyncio.create_task(_run_room_server(stop_event, ready_event))
    await asyncio.wait_for(ready_event.wait(), 5.0)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws:
            tok = await _register_and_login(ws, "room_err_alice")
            join_env = Envelope(
                type=MessageType.ROOM_JOIN,
                payload={"session_token": tok, "room_id": "BADXXX"},
            )
            await ws.send(join_env.to_json())
            r = Envelope.from_json(await asyncio.wait_for(ws.recv(), 3.0))
            assert r.type == MessageType.ROOM_ERROR
    finally:
        stop_event.set()
        await srv
