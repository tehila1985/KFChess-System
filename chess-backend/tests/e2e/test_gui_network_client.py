"""
e2e test for client/gui/network_client.py — NetworkClient.

Validates the thread/asyncio boundary for real: NetworkClient runs its own
event loop on a background thread; this test drives it against a real
websocket server (room create/join flow) and checks that request() returns
a correct response across the thread boundary, and that poll_events()
correctly delivers a push-style message (GAME_START, sent unprompted after
the second player joins) that arrived on the background thread.
"""
from __future__ import annotations

import asyncio
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
from common.protocol.schemas import (
    Envelope, RegisterPayload, LoginPayload, RoomCreatePayload, RoomJoinPayload,
)
from client.gui.network_client import NetworkClient
from client.logging_.client_logger import ClientLogger

TEST_PORT = 18773


async def _run_room_server(stop_event: asyncio.Event, ready_event: asyncio.Event):
    settings = load_settings()
    raw_logger = logging.getLogger("chess.test.gui_network")
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
async def test_network_client_request_and_poll_events_across_thread():
    """
    NetworkClient.start()/.request() are deliberately *synchronous, blocking*
    calls — that's the whole point (see network_client.py's docstring): the
    real GUI calls them from a plain synchronous main(), no event loop
    involved on that thread at all. But this test's server also runs on
    the test's own event loop, so calling those blocking methods directly
    from this coroutine would freeze that very loop and deadlock (the
    server could never process the handshake it's waiting to accept).
    run_in_executor offloads them to a worker thread instead, exactly like
    a real synchronous caller would experience them.
    """
    stop_event = asyncio.Event()
    ready_event = asyncio.Event()
    srv = asyncio.create_task(_run_room_server(stop_event, ready_event))
    await asyncio.wait_for(ready_event.wait(), 5.0)

    loop = asyncio.get_event_loop()
    network = NetworkClient(
        uri=f"ws://127.0.0.1:{TEST_PORT}",
        client_logger=ClientLogger(logging.getLogger("chess.test.gui_network.client")),
    )

    try:
        await loop.run_in_executor(None, network.start, 5.0)

        # request() must work synchronously from the calling (main) thread
        # even though NetworkClient runs its socket on a background thread.
        reg_resp = await loop.run_in_executor(None, network.request, Envelope(
            type=MessageType.REGISTER,
            payload=RegisterPayload(username="gui_alice", password="password123").model_dump(),
        ))
        assert reg_resp.type == MessageType.REGISTER_OK

        login_resp = await loop.run_in_executor(None, network.request, Envelope(
            type=MessageType.LOGIN,
            payload=LoginPayload(username="gui_alice", password="password123").model_dump(),
        ))
        assert login_resp.type == MessageType.LOGIN_OK
        token = login_resp.payload["session_token"]
        network.session.set_auth(token, "gui_alice", login_resp.payload["elo"])

        create_resp = await loop.run_in_executor(None, network.request, Envelope(
            type=MessageType.ROOM_CREATE,
            payload=RoomCreatePayload(session_token=token).model_dump(),
        ))
        assert create_resp.type == MessageType.ROOM_CREATED
        room_id = create_resp.payload["room_id"]

        # No push events yet — nobody has joined.
        assert network.poll_events() == []

        # A second (plain websockets) client joins the room — this should
        # trigger GAME_START pushed to gui_alice, picked up via poll_events().
        async with websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws2:
            await ws2.send(Envelope(
                type=MessageType.REGISTER,
                payload={"username": "gui_bob", "password": "password123"},
            ).to_json())
            await asyncio.wait_for(ws2.recv(), 3.0)
            await ws2.send(Envelope(
                type=MessageType.LOGIN,
                payload={"username": "gui_bob", "password": "password123"},
            ).to_json())
            login2 = Envelope.from_json(await asyncio.wait_for(ws2.recv(), 3.0))
            tok2 = login2.payload["session_token"]

            await ws2.send(Envelope(
                type=MessageType.ROOM_JOIN,
                payload={"session_token": tok2, "room_id": room_id},
            ).to_json())
            await asyncio.wait_for(ws2.recv(), 3.0)  # ROOM_ROLE_ASSIGNED
            await asyncio.wait_for(ws2.recv(), 3.0)  # GAME_START (bob's own)

            # Give the background thread a moment to receive and enqueue.
            events = []
            for _ in range(20):
                events = network.poll_events()
                if events:
                    break
                await asyncio.sleep(0.1)

        assert any(e.type == MessageType.GAME_START for e in events), events
        game_start = next(e for e in events if e.type == MessageType.GAME_START)
        assert game_start.payload["room_id"] == room_id
        assert "board" in game_start.payload
    finally:
        network.stop()
        stop_event.set()
        await srv
