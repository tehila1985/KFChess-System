"""
Phase 2 e2e test (.github/Server_Design_Implementation_Plan.md): starts a
real gateway/main.py process and a real shard/main.py process (actual OS
subprocesses, not asyncio tasks in this test's own process — "kill the
process" needs to mean a real process kill for the failure-mode assertions
to be meaningful) connected over the real NATS/Redis containers from
docker-compose.yml, and drives the existing full room+game scenario across
that process boundary exactly like the monolith's own e2e tests do against
server.main.serve().

Skipped, not failed, if Redis or NATS aren't reachable.

Two independent scenarios (deliberately not chained — GameSession state
lives only in the Shard process's memory in Phase 2, so a killed Shard's
game is gone for good; that's a fact about *this* scenario, not something
the Gateway restart scenario should also inherit):

- test_killing_shard_mid_game_is_observed_as_shard_unavailable: the Gateway's
  heartbeat watchdog detects a hard-killed Shard and raises a client-visible
  ERROR("shard_unavailable") — Server_Design.md §1 Q4 / §5's "aborted"
  outcome. A Gateway can only ever raise a signal, never itself persist a
  GameRecord, since the Shard holding that authority is gone with it.
- test_killing_gateway_and_reconnecting_resumes_the_game: the Shard is never
  touched; only the Gateway is killed and replaced by a freshly started one.
  Proves the Redis-backed session directory (not gateway-local state) is
  what makes reconnect work, and exercises the GameSession.handle_reconnect
  fix from this same phase.
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import asynccontextmanager

import pytest
import websockets
import yaml
import redis as redis_lib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://localhost:6380/0")
NATS_TEST_URL = os.environ.get("NATS_TEST_URL", "nats://localhost:4222")


def _redis_reachable() -> bool:
    try:
        client = redis_lib.Redis.from_url(REDIS_TEST_URL, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


def _nats_reachable() -> bool:
    # nats://host:port — a bare TCP connect is enough to know something's listening.
    rest = NATS_TEST_URL.split("://", 1)[-1]
    host, _, port = rest.partition(":")
    try:
        with socket.create_connection((host, int(port or 4222)), timeout=1):
            return True
    except Exception:
        return False


INFRA_UP = _redis_reachable() and _nats_reachable()
pytestmark = pytest.mark.skipif(not INFRA_UP, reason=f"redis/nats not reachable ({REDIS_TEST_URL}, {NATS_TEST_URL})")


def _write_temp_config(port: int, db_path: str) -> str:
    with open(os.path.join(BACKEND_DIR, "config", "default.yaml"), encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config["server"]["port"] = port
    config["server"]["db_path"] = db_path
    fd, path = tempfile.mkstemp(suffix=".yaml", prefix="chess_test_config_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)
    return path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spawn(module: str, config_path: str, shard_id: str, log_path: str) -> subprocess.Popen:
    env = dict(os.environ)
    env["CHESS_CONFIG_PATH"] = config_path
    env["REDIS_URL"] = REDIS_TEST_URL
    env["NATS_URL"] = NATS_TEST_URL
    env["SHARD_ID"] = shard_id
    log_file = open(log_path, "w", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-m", module],
        cwd=BACKEND_DIR, env=env, stdout=log_file, stderr=subprocess.STDOUT,
    )


def _kill(proc: subprocess.Popen) -> None:
    if proc is not None and proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


async def _connect_with_retry(uri, attempts=40, delay=0.1):
    last_exc = None
    for _ in range(attempts):
        try:
            return await websockets.connect(uri)
        except OSError as exc:
            last_exc = exc
            await asyncio.sleep(delay)
    raise last_exc


async def _register_and_login(ws, username, password="password123"):
    await ws.send(Envelope(
        type=MessageType.REGISTER, payload={"username": username, "password": password},
    ).to_json())
    await asyncio.wait_for(ws.recv(), 5.0)
    return await _login(ws, username, password)


async def _login(ws, username, password="password123"):
    await ws.send(Envelope(
        type=MessageType.LOGIN, payload={"username": username, "password": password},
    ).to_json())
    resp = Envelope.from_json(await asyncio.wait_for(ws.recv(), 5.0))
    assert resp.type == MessageType.LOGIN_OK
    return resp.payload["session_token"]


@asynccontextmanager
async def _gateway_shard_stack(run_id: str):
    """Starts a fresh Shard + Gateway pair on a scratch config; tears both down on exit."""
    shard_id = f"shard-test-{run_id}"
    port = _free_port()
    db_path = os.path.join(tempfile.gettempdir(), f"chess_test_{run_id}.db")
    config_path = _write_temp_config(port, db_path=db_path)
    shard_log = os.path.join(tempfile.gettempdir(), f"shard_{run_id}.log")
    gateway_log = os.path.join(tempfile.gettempdir(), f"gateway_{run_id}.log")

    shard_proc = _spawn("shard.main", config_path, shard_id, shard_log)
    await asyncio.sleep(1.0)  # let the shard subscribe before the gateway starts publishing
    gateway_proc = _spawn("gateway.main", config_path, shard_id, gateway_log)

    ctx = {
        "port": port, "shard_id": shard_id, "config_path": config_path, "db_path": db_path,
        "shard_log": shard_log, "gateway_log": gateway_log,
        "shard_proc": shard_proc, "gateway_proc": gateway_proc,
    }
    try:
        yield ctx
    finally:
        _kill(ctx["shard_proc"])
        _kill(ctx["gateway_proc"])
        for path in (config_path, db_path):
            try:
                os.remove(path)
            except OSError:
                pass


async def _start_two_player_game(uri, run_id):
    """Register+login two players, create+join a room, drain both GAME_START frames."""
    ws_a = await _connect_with_retry(uri)
    ws_b = await _connect_with_retry(uri)
    tok_a = await _register_and_login(ws_a, f"alice_{run_id}")
    tok_b = await _register_and_login(ws_b, f"bob_{run_id}")

    await ws_a.send(Envelope(
        type=MessageType.ROOM_CREATE, payload={"session_token": tok_a},
    ).to_json())
    create_resp = Envelope.from_json(await asyncio.wait_for(ws_a.recv(), 5.0))
    room_id = create_resp.payload["room_id"]

    await ws_b.send(Envelope(
        type=MessageType.ROOM_JOIN, payload={"session_token": tok_b, "room_id": room_id},
    ).to_json())
    join_resp = Envelope.from_json(await asyncio.wait_for(ws_b.recv(), 5.0))
    assert join_resp.payload["role"] == "black"

    start_a = Envelope.from_json(await asyncio.wait_for(ws_a.recv(), 5.0))
    start_b = Envelope.from_json(await asyncio.wait_for(ws_b.recv(), 5.0))
    assert start_a.type == MessageType.GAME_START
    assert start_b.type == MessageType.GAME_START
    return ws_a, ws_b, tok_a, tok_b


@pytest.mark.asyncio
async def test_full_game_across_gateway_shard_boundary():
    run_id = uuid.uuid4().hex[:8]
    async with _gateway_shard_stack(run_id) as ctx:
        uri = f"ws://127.0.0.1:{ctx['port']}"
        ws_a, ws_b, tok_a, tok_b = await _start_two_player_game(uri, run_id)
        try:
            # A real move, round-tripping Gateway -> NATS -> Shard -> NATS -> Gateway.
            # ws_a is both the mover (gets MOVE_ACK) and a broadcast target
            # (gets MOVE_BROADCAST) — publish order across two NATS hops
            # isn't guaranteed, so accept either arrival order.
            await ws_a.send(Envelope(
                type=MessageType.MOVE,
                payload={"session_token": tok_a, "src_row": 6, "src_col": 4, "dst_row": 4, "dst_col": 4},
            ).to_json())
            seen_types_a = set()
            ack_payload = None
            for _ in range(2):
                env = Envelope.from_json(await asyncio.wait_for(ws_a.recv(), 5.0))
                seen_types_a.add(env.type)
                if env.type == MessageType.MOVE_ACK:
                    ack_payload = env.payload
            assert {MessageType.MOVE_ACK, MessageType.MOVE_BROADCAST} == seen_types_a
            assert ack_payload["status"] == "accepted"
            broadcast_b = Envelope.from_json(await asyncio.wait_for(ws_b.recv(), 5.0))
            assert broadcast_b.type == MessageType.MOVE_BROADCAST
        finally:
            await ws_a.close()
            await ws_b.close()


@pytest.mark.asyncio
async def test_killing_shard_mid_game_is_observed_as_shard_unavailable():
    run_id = uuid.uuid4().hex[:8]
    async with _gateway_shard_stack(run_id) as ctx:
        uri = f"ws://127.0.0.1:{ctx['port']}"
        ws_a, ws_b, _, _ = await _start_two_player_game(uri, run_id)
        try:
            ctx["shard_proc"].kill()
            ctx["shard_proc"].wait(timeout=10)

            saw_shard_unavailable = False
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline and not saw_shard_unavailable:
                try:
                    raw = await asyncio.wait_for(ws_a.recv(), max(0.1, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                env = Envelope.from_json(raw)
                if env.type == MessageType.ERROR and env.payload.get("reason") == "shard_unavailable":
                    saw_shard_unavailable = True
            assert saw_shard_unavailable, "expected an ERROR(shard_unavailable) after killing the shard process"
        finally:
            await ws_a.close()
            await ws_b.close()


@pytest.mark.asyncio
async def test_killing_gateway_and_reconnecting_resumes_the_game():
    run_id = uuid.uuid4().hex[:8]
    async with _gateway_shard_stack(run_id) as ctx:
        uri = f"ws://127.0.0.1:{ctx['port']}"
        ws_a, ws_b, tok_a, _ = await _start_two_player_game(uri, run_id)
        try:
            # Kill only the Gateway — the Shard (and its in-memory GameSession)
            # keeps running the whole time, exactly like Server_Design.md's
            # "many Gateways, few Shards" topology: losing one Gateway must
            # not lose the game it was relaying.
            await ws_a.close()
            ctx["gateway_proc"].kill()
            ctx["gateway_proc"].wait(timeout=10)

            new_gateway = _spawn("gateway.main", ctx["config_path"], ctx["shard_id"], ctx["gateway_log"])
            ctx["gateway_proc"] = new_gateway

            ws_a = await _connect_with_retry(uri)
            new_tok_a = await _login(ws_a, f"alice_{run_id}")
            # Login always mints a brand-new session_token — reconnect is
            # correlated by user_id, not by this token equalling the old one.

            # The reconnected player must be able to move again in the SAME
            # game — proves GameSession.handle_reconnect really re-pointed
            # both conn_id and session_token.
            await ws_a.send(Envelope(
                type=MessageType.MOVE,
                payload={"session_token": new_tok_a, "src_row": 6, "src_col": 3, "dst_row": 5, "dst_col": 3},
            ).to_json())
            ack_payload = None
            for _ in range(2):
                env = Envelope.from_json(await asyncio.wait_for(ws_a.recv(), 5.0))
                if env.type == MessageType.MOVE_ACK:
                    ack_payload = env.payload
            assert ack_payload is not None, "no MOVE_ACK after reconnect"
            assert ack_payload["status"] == "accepted", ack_payload
            # Note: bob (ws_b) was connected through the same now-dead
            # Gateway process and never reconnected in this test — his
            # socket is gone too, same as any real client whose Gateway
            # instance disappears. Only alice's reconnect is under test here.
        finally:
            await ws_a.close()
            try:
                await ws_b.close()
            except Exception:
                pass
