"""
Phase 1 unit tests: config loader, LoggerFactory, protocol envelope,
ConnectionHub, and MessageRouter (PING→PONG).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import uuid

import pytest

# Make chess-backend importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.config_loader import load_settings, Settings
from server.logging_.logger_factory import LoggerFactory, build_logger
from server.connection_hub import ConnectionHub
from server.message_router import MessageRouter
from server.handlers.system_handler import make_ping_handler
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, ErrorPayload


# ── Config loader ────────────────────────────────────────────────────────────

class TestConfigLoader:
    def test_loads_defaults(self):
        settings = load_settings()
        assert isinstance(settings, Settings)
        assert settings.rating.starting_elo == 1200
        assert settings.rating.k_factor == 32
        assert settings.rating.match_range == 100
        assert settings.matchmaking.queue_timeout_seconds == 60
        assert settings.game.disconnect_grace_seconds == 20
        assert settings.room.id_length == 6
        assert settings.auth.min_password_length == 8
        assert settings.server.port == 8765

    def test_all_tunables_present(self):
        settings = load_settings()
        # Ensure no attribute is None for core tunables
        assert settings.rating.starting_elo is not None
        assert settings.matchmaking.poll_interval_seconds is not None
        assert settings.game.countdown_tick_seconds is not None
        assert settings.room.id_alphabet is not None
        assert settings.logging.level is not None


# ── Logger factory ───────────────────────────────────────────────────────────

class TestLoggerFactory:
    def test_builds_server_logger(self, tmp_path):
        factory = LoggerFactory(level="DEBUG")
        log_path = str(tmp_path / "server.log")
        logger = factory.get_server_logger(log_path)
        assert isinstance(logger, logging.Logger)
        assert logger.name == "chess.server"

    def test_builds_client_logger(self, tmp_path):
        factory = LoggerFactory(level="DEBUG")
        log_path = str(tmp_path / "client.log")
        logger = factory.get_client_logger(log_path)
        assert isinstance(logger, logging.Logger)
        assert logger.name == "chess.client"

    def test_writes_json_to_file(self, tmp_path):
        log_path = str(tmp_path / "test.log")
        logger = build_logger("test.json", log_path, level="DEBUG")
        logger.info("hello world")
        with open(log_path, encoding="utf-8") as f:
            line = f.readline()
        data = json.loads(line)
        assert data["level"] == "INFO"
        assert "hello world" in data["msg"]
        assert "ts" in data


# ── Protocol envelope ────────────────────────────────────────────────────────

class TestEnvelope:
    def test_round_trip(self):
        env = Envelope(type=MessageType.PING, payload={})
        raw = env.to_json()
        env2 = Envelope.from_json(raw)
        assert env2.type == MessageType.PING
        assert env2.request_id == env.request_id

    def test_request_id_auto_generated(self):
        env1 = Envelope(type=MessageType.PONG)
        env2 = Envelope(type=MessageType.PONG)
        assert env1.request_id != env2.request_id

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            Envelope.from_json("not json")

    def test_unknown_type_raises(self):
        with pytest.raises(Exception):
            Envelope.from_json('{"type": "NONEXISTENT_TYPE", "request_id": "abc", "payload": {}}')


# ── ConnectionHub ────────────────────────────────────────────────────────────

class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.remote_address = ("127.0.0.1", 12345)

    async def send(self, msg: str):
        self.sent.append(msg)


class TestConnectionHub:
    def test_register_and_lookup(self):
        hub = ConnectionHub()
        ws = FakeWebSocket()
        hub.register("c1", ws)
        assert hub.get_websocket("c1") is ws
        assert hub.is_connected("c1")

    def test_unregister_removes_connection(self):
        hub = ConnectionHub()
        ws = FakeWebSocket()
        hub.register("c1", ws)
        hub.unregister("c1")
        assert not hub.is_connected("c1")
        assert hub.get_websocket("c1") is None

    def test_associate_and_lookup_token(self):
        hub = ConnectionHub()
        ws = FakeWebSocket()
        hub.register("c1", ws)
        hub.associate_token("c1", "tok123")
        assert hub.get_conn_id_by_token("tok123") == "c1"
        assert hub.get_token_by_conn_id("c1") == "tok123"

    def test_unregister_cleans_up_token(self):
        hub = ConnectionHub()
        ws = FakeWebSocket()
        hub.register("c1", ws)
        hub.associate_token("c1", "tok123")
        hub.unregister("c1")
        assert hub.get_conn_id_by_token("tok123") is None

    def test_disconnect_callback_fired(self):
        hub = ConnectionHub()
        ws = FakeWebSocket()
        hub.register("c1", ws)
        fired = []
        hub.on_disconnect(lambda cid: fired.append(cid))
        hub.unregister("c1")
        assert fired == ["c1"]

    @pytest.mark.asyncio
    async def test_send(self):
        hub = ConnectionHub()
        ws = FakeWebSocket()
        hub.register("c1", ws)
        result = await hub.send("c1", '{"type": "PONG"}')
        assert result is True
        assert ws.sent == ['{"type": "PONG"}']

    @pytest.mark.asyncio
    async def test_send_to_missing_conn_returns_false(self):
        hub = ConnectionHub()
        result = await hub.send("nope", "msg")
        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast(self):
        hub = ConnectionHub()
        ws1, ws2 = FakeWebSocket(), FakeWebSocket()
        hub.register("c1", ws1)
        hub.register("c2", ws2)
        await hub.broadcast({"c1", "c2"}, "hello")
        assert ws1.sent == ["hello"]
        assert ws2.sent == ["hello"]


# ── MessageRouter ────────────────────────────────────────────────────────────

class TestMessageRouter:
    @pytest.mark.asyncio
    async def test_ping_pong(self):
        hub = ConnectionHub()
        ws = FakeWebSocket()
        hub.register("c1", ws)
        router = MessageRouter(hub=hub, logger=logging.getLogger("test"))
        router.register(MessageType.PING, make_ping_handler(hub, logging.getLogger("test")))

        ping = Envelope(type=MessageType.PING, payload={})
        await router.route("c1", ping.to_json())

        assert len(ws.sent) == 1
        resp = Envelope.from_json(ws.sent[0])
        assert resp.type == MessageType.PONG
        assert resp.request_id == ping.request_id

    @pytest.mark.asyncio
    async def test_invalid_json_sends_error(self):
        hub = ConnectionHub()
        ws = FakeWebSocket()
        hub.register("c1", ws)
        router = MessageRouter(hub=hub, logger=logging.getLogger("test"))
        await router.route("c1", "not-json")
        assert len(ws.sent) == 1
        resp = Envelope.from_json(ws.sent[0])
        assert resp.type == MessageType.ERROR

    @pytest.mark.asyncio
    async def test_unknown_message_type_sends_error(self):
        hub = ConnectionHub()
        ws = FakeWebSocket()
        hub.register("c1", ws)
        router = MessageRouter(hub=hub, logger=logging.getLogger("test"))
        # PING registered nowhere, so MOVE is unknown
        env = Envelope(type=MessageType.MOVE, payload={})
        await router.route("c1", env.to_json())
        assert len(ws.sent) == 1
        resp = Envelope.from_json(ws.sent[0])
        assert resp.type == MessageType.ERROR
