"""
Phase 1 integration test: real WebSocket server PING → PONG.
"""
from __future__ import annotations

import asyncio
import sys
import os
import uuid

import pytest
import websockets

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.config_loader import load_settings
from server.connection_hub import ConnectionHub
from server.message_router import MessageRouter
from server.handlers.system_handler import make_ping_handler
from server.logging_.server_logger import build_server_logger
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope

import logging


TEST_PORT = 18765


async def _run_test_server(stop_event: asyncio.Event):
    """Minimal server for integration tests."""
    settings = load_settings()
    raw_logger = logging.getLogger("chess.test.server")
    hub = ConnectionHub(logger=raw_logger)
    router = MessageRouter(hub=hub, logger=raw_logger)
    router.register(MessageType.PING, make_ping_handler(hub, raw_logger))

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
async def test_ping_pong_integration():
    stop_event = asyncio.Event()
    server_task = asyncio.create_task(_run_test_server(stop_event))
    # Give server time to start
    await asyncio.sleep(0.1)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws:
            ping = Envelope(type=MessageType.PING, payload={})
            await ws.send(ping.to_json())
            raw_resp = await asyncio.wait_for(ws.recv(), timeout=3.0)
            resp = Envelope.from_json(raw_resp)
            assert resp.type == MessageType.PONG
            assert resp.request_id == ping.request_id
    finally:
        stop_event.set()
        await server_task


@pytest.mark.asyncio
async def test_multiple_pings():
    stop_event = asyncio.Event()
    server_task = asyncio.create_task(_run_test_server(stop_event))
    await asyncio.sleep(0.1)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws:
            for _ in range(3):
                ping = Envelope(type=MessageType.PING, payload={})
                await ws.send(ping.to_json())
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                resp = Envelope.from_json(raw)
                assert resp.type == MessageType.PONG
    finally:
        stop_event.set()
        await server_task


@pytest.mark.asyncio
async def test_invalid_message_returns_error():
    stop_event = asyncio.Event()
    server_task = asyncio.create_task(_run_test_server(stop_event))
    await asyncio.sleep(0.1)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws:
            await ws.send("not-json-at-all")
            raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
            resp = Envelope.from_json(raw)
            assert resp.type == MessageType.ERROR
    finally:
        stop_event.set()
        await server_task
