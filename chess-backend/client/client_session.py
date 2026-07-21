"""
client_session.py — owns the WebSocket connection, send/receive, correlation.

SRP: networking only. No business logic, no UI rendering.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable, Coroutine, Dict, Optional

import websockets

from common.protocol.schemas import Envelope
from common.protocol.message_types import MessageType
from client.logging_.client_logger import ClientLogger


class ClientSession:
    """
    Manages a single WebSocket connection to the server.

    Handles:
    - Connecting and disconnecting
    - Sending envelopes and correlating responses via request_id
    - Routing incoming messages to registered handlers
    """

    def __init__(self, uri: str, client_logger: ClientLogger) -> None:
        self._uri = uri
        self._log = client_logger
        self._ws: Optional[Any] = None
        self._handlers: Dict[MessageType, Callable] = {}
        self._pending: Dict[str, asyncio.Future] = {}  # request_id → Future
        self._session_token: Optional[str] = None
        self._username: Optional[str] = None
        self._elo: Optional[int] = None

    # ── Auth state ────────────────────────────────────────────────────

    @property
    def session_token(self) -> Optional[str]:
        return self._session_token

    @property
    def username(self) -> Optional[str]:
        return self._username

    @property
    def elo(self) -> Optional[int]:
        return self._elo

    def set_auth(self, token: str, username: str, elo: int) -> None:
        self._session_token = token
        self._username = username
        self._elo = elo

    def is_authenticated(self) -> bool:
        return self._session_token is not None

    # ── Connection ────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._uri)
        self._log.info("connected uri=%s" % self._uri)

    async def disconnect(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    # ── Handlers ──────────────────────────────────────────────────────

    def on(self, msg_type: MessageType, handler: Callable) -> None:
        """Register a handler for incoming messages of msg_type."""
        self._handlers[msg_type] = handler

    # ── Send ──────────────────────────────────────────────────────────

    async def send(self, envelope: Envelope) -> None:
        if self._ws is None:
            raise RuntimeError("Not connected")
        raw = envelope.to_json()
        self._log.message_sent(envelope.type.value, envelope.request_id)
        await self._ws.send(raw)

    async def request(self, envelope: Envelope, timeout: float = 10.0) -> Envelope:
        """Send an envelope and wait for the correlated response."""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[envelope.request_id] = fut
        try:
            await self.send(envelope)
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(envelope.request_id, None)

    # ── Receive loop ──────────────────────────────────────────────────

    async def receive_loop(self) -> None:
        """Run until the connection is closed, dispatching each message."""
        if self._ws is None:
            raise RuntimeError("Not connected")
        try:
            async for raw in self._ws:
                await self._dispatch(raw)
        except websockets.exceptions.ConnectionClosed as exc:
            self._log.connection_drop(str(exc))

    async def _dispatch(self, raw: str) -> None:
        try:
            env = Envelope.from_json(raw)
        except Exception as exc:
            self._log.render_error("dispatch", str(exc))
            return

        self._log.message_received(env.type.value, env.request_id)

        # Resolve pending requests first
        fut = self._pending.get(env.request_id)
        if fut is not None and not fut.done():
            fut.set_result(env)
            return

        # Then dispatch to registered handlers
        handler = self._handlers.get(env.type)
        if handler is not None:
            try:
                result = handler(env)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                self._log.render_error(env.type.value, str(exc))
