"""
Phase 1 e2e test (.github/Server_Design_Implementation_Plan.md): runs the
real server.main.serve() entrypoint — the same one python -m server.main
uses — configured via the settings.backend.redis_enabled flag, and drives a
real two-client room+game flow through it exactly like the existing
same-process test suite already does for the in-memory backend.

Requires a real Redis reachable at REDIS_TEST_URL (this repo's
docker-compose.yml redis service, localhost:6380 by default). Skipped, not
failed, if unreachable.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import sys
import uuid

import pytest
import websockets

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import redis as redis_lib

from server.config_loader import load_settings
from server.main import serve
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope

REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://localhost:6380/0")
TEST_PORT = 18790


def _redis_reachable() -> bool:
    try:
        client = redis_lib.Redis.from_url(REDIS_TEST_URL, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


REDIS_UP = _redis_reachable()


def _redis_backed_settings(run_id: str):
    base = load_settings()
    return dataclasses.replace(
        base,
        server=dataclasses.replace(base.server, port=TEST_PORT, db_path=":memory:"),
        backend=dataclasses.replace(
            base.backend,
            redis_enabled=True,
            redis_url=REDIS_TEST_URL,
            session_key_prefix=f"e2e:{run_id}:session",
            room_key_prefix=f"e2e:{run_id}:room",
            match_queue_key=f"e2e:{run_id}:queue",
        ),
    )


async def _connect_with_retry(uri, attempts=20, delay=0.05):
    last_exc = None
    for _ in range(attempts):
        try:
            return await websockets.connect(uri)
        except OSError as exc:
            last_exc = exc
            await asyncio.sleep(delay)
    raise last_exc


async def _register_and_login(ws, username):
    await ws.send(Envelope(
        type=MessageType.REGISTER, payload={"username": username, "password": "password123"},
    ).to_json())
    await asyncio.wait_for(ws.recv(), 3.0)
    await ws.send(Envelope(
        type=MessageType.LOGIN, payload={"username": username, "password": "password123"},
    ).to_json())
    resp = Envelope.from_json(await asyncio.wait_for(ws.recv(), 3.0))
    assert resp.type == MessageType.LOGIN_OK
    return resp.payload["session_token"]


@pytest.mark.asyncio
async def test_server_main_serve_with_redis_backend_runs_a_full_room_game():
    if not REDIS_UP:
        pytest.skip(f"redis not reachable at {REDIS_TEST_URL}")

    run_id = uuid.uuid4().hex[:8]
    settings = _redis_backed_settings(run_id)
    server_task = asyncio.create_task(serve(settings=settings))
    try:
        uri = f"ws://127.0.0.1:{TEST_PORT}"
        ws_a = await _connect_with_retry(uri)
        ws_b = await _connect_with_retry(uri)
        try:
            tok_a = await _register_and_login(ws_a, f"alice_{run_id}")
            tok_b = await _register_and_login(ws_b, f"bob_{run_id}")

            await ws_a.send(Envelope(
                type=MessageType.ROOM_CREATE, payload={"session_token": tok_a},
            ).to_json())
            create_resp = Envelope.from_json(await asyncio.wait_for(ws_a.recv(), 3.0))
            room_id = create_resp.payload["room_id"]

            await ws_b.send(Envelope(
                type=MessageType.ROOM_JOIN, payload={"session_token": tok_b, "room_id": room_id},
            ).to_json())
            join_resp = Envelope.from_json(await asyncio.wait_for(ws_b.recv(), 3.0))
            assert join_resp.payload["role"] == "black"

            # GAME_START should reach both — proves the room really started a
            # game using the Redis-backed registry, not silently falling back.
            start_a = Envelope.from_json(await asyncio.wait_for(ws_a.recv(), 3.0))
            start_b = Envelope.from_json(await asyncio.wait_for(ws_b.recv(), 3.0))
            assert start_a.type == MessageType.GAME_START
            assert start_b.type == MessageType.GAME_START

            # Directly confirm the room really lives in Redis, per Server_Design.md
            # §1 Q2's "room:{room_id}" key shape.
            client = redis_lib.Redis.from_url(REDIS_TEST_URL, decode_responses=True)
            assert client.exists(f"e2e:{run_id}:room:{room_id}")
        finally:
            await ws_a.close()
            await ws_b.close()
    finally:
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass
