"""
message_router.py — decodes the envelope, dispatches to handler by MessageType.

SRP: routing only. Knows which handler handles which type; does not implement
any business logic itself.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, ErrorPayload


HandlerFunc = Callable[[str, Envelope], Coroutine[Any, Any, None]]


class MessageRouter:
    """
    Decodes incoming JSON, validates the envelope, and dispatches to
    the registered handler for the given MessageType.

    Usage:
        router = MessageRouter(hub, logger)
        router.register(MessageType.PING, ping_handler)
        await router.route(conn_id, raw_json)
    """

    def __init__(self, hub: Any, logger: Optional[logging.Logger] = None) -> None:
        self._hub = hub
        self._handlers: Dict[MessageType, HandlerFunc] = {}
        self._log = logger or logging.getLogger(__name__)

    def register(self, msg_type: MessageType, handler: HandlerFunc) -> None:
        """Register a handler coroutine for the given message type."""
        self._handlers[msg_type] = handler

    async def route(self, conn_id: str, raw: str) -> None:
        """
        Parse raw JSON into an Envelope and dispatch to the registered handler.

        Sends an ERROR response back on any parse or dispatch failure.
        """
        try:
            envelope = Envelope.from_json(raw)
        except Exception as exc:
            self._log.warning("envelope_parse_error conn_id=%s exc=%s", conn_id, exc)
            await self._send_error(conn_id, "invalid_envelope", str(exc))
            return

        handler = self._handlers.get(envelope.type)
        if handler is None:
            self._log.warning(
                "no_handler conn_id=%s type=%s", conn_id, envelope.type
            )
            await self._send_error(conn_id, "unknown_message_type", envelope.type)
            return

        try:
            await handler(conn_id, envelope)
        except Exception as exc:
            self._log.exception("handler_error conn_id=%s type=%s", conn_id, envelope.type)
            await self._send_error(conn_id, "internal_error", str(exc))

    async def _send_error(self, conn_id: str, code: str, reason: str) -> None:
        error_env = Envelope(
            type=MessageType.ERROR,
            payload=ErrorPayload(reason=reason, code=code).model_dump(),
        )
        await self._hub.send(conn_id, error_env.to_json())
