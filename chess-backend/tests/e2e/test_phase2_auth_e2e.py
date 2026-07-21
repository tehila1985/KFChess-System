"""
Phase 2 e2e tests: register and login via a real WebSocket server.
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

from server.config_loader import load_settings
from server.connection_hub import ConnectionHub
from server.message_router import MessageRouter
from server.handlers.system_handler import make_ping_handler
from server.handlers.auth_handler import AuthHandler
from server.services.auth_service import AuthService
from server.repositories.user_repository import UserRepository
from server.db.database import get_connection
from server.logging_.server_logger import build_server_logger
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope

TEST_PORT = 18766


async def _run_auth_server(stop_event: asyncio.Event):
    settings = load_settings()
    raw_logger = logging.getLogger("chess.test.auth")
    conn = get_connection(":memory:")
    repo = UserRepository(conn)
    auth_svc = AuthService(repo=repo, settings=settings, logger=raw_logger)
    hub = ConnectionHub(logger=raw_logger)
    router = MessageRouter(hub=hub, logger=raw_logger)
    auth_handler = AuthHandler(auth_service=auth_svc, hub=hub, logger=raw_logger)

    router.register(MessageType.PING, make_ping_handler(hub, raw_logger))
    router.register(MessageType.LOGIN, auth_handler.make_login_handler())
    router.register(MessageType.REGISTER, auth_handler.make_register_handler())

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
        await stop_event.wait()


@pytest.mark.asyncio
async def test_register_ok():
    stop_event = asyncio.Event()
    srv = asyncio.create_task(_run_auth_server(stop_event))
    await asyncio.sleep(0.1)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws:
            env = Envelope(
                type=MessageType.REGISTER,
                payload={"username": "alice", "password": "mypassword123"},
            )
            await ws.send(env.to_json())
            resp = Envelope.from_json(await asyncio.wait_for(ws.recv(), 3.0))
            assert resp.type == MessageType.REGISTER_OK
            assert resp.payload["username"] == "alice"
    finally:
        stop_event.set()
        await srv


@pytest.mark.asyncio
async def test_register_duplicate_fails():
    stop_event = asyncio.Event()
    srv = asyncio.create_task(_run_auth_server(stop_event))
    await asyncio.sleep(0.1)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws:
            env1 = Envelope(
                type=MessageType.REGISTER,
                payload={"username": "bob", "password": "bobspass123"},
            )
            await ws.send(env1.to_json())
            await asyncio.wait_for(ws.recv(), 3.0)

            env2 = Envelope(
                type=MessageType.REGISTER,
                payload={"username": "bob", "password": "bobspass456"},
            )
            await ws.send(env2.to_json())
            resp = Envelope.from_json(await asyncio.wait_for(ws.recv(), 3.0))
            assert resp.type == MessageType.REGISTER_ERROR
    finally:
        stop_event.set()
        await srv


@pytest.mark.asyncio
async def test_login_after_register():
    stop_event = asyncio.Event()
    srv = asyncio.create_task(_run_auth_server(stop_event))
    await asyncio.sleep(0.1)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws:
            # Register
            reg = Envelope(
                type=MessageType.REGISTER,
                payload={"username": "carol", "password": "carolpass123"},
            )
            await ws.send(reg.to_json())
            await asyncio.wait_for(ws.recv(), 3.0)

            # Login
            login = Envelope(
                type=MessageType.LOGIN,
                payload={"username": "carol", "password": "carolpass123"},
            )
            await ws.send(login.to_json())
            resp = Envelope.from_json(await asyncio.wait_for(ws.recv(), 3.0))
            assert resp.type == MessageType.LOGIN_OK
            assert resp.payload["username"] == "carol"
            assert "session_token" in resp.payload
            assert resp.payload["elo"] == 1200
    finally:
        stop_event.set()
        await srv


@pytest.mark.asyncio
async def test_login_wrong_password():
    stop_event = asyncio.Event()
    srv = asyncio.create_task(_run_auth_server(stop_event))
    await asyncio.sleep(0.1)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws:
            reg = Envelope(
                type=MessageType.REGISTER,
                payload={"username": "dave", "password": "davepass123"},
            )
            await ws.send(reg.to_json())
            await asyncio.wait_for(ws.recv(), 3.0)

            login = Envelope(
                type=MessageType.LOGIN,
                payload={"username": "dave", "password": "wrongpass"},
            )
            await ws.send(login.to_json())
            resp = Envelope.from_json(await asyncio.wait_for(ws.recv(), 3.0))
            assert resp.type == MessageType.LOGIN_ERROR
    finally:
        stop_event.set()
        await srv
