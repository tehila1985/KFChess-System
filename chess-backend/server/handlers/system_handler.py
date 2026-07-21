"""
system_handler.py — handles PING → PONG.
"""
from __future__ import annotations

import logging
from typing import Any

from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope


async def handle_ping(conn_id: str, envelope: Envelope, hub: Any,
                       logger: logging.Logger) -> None:
    """Respond to PING with PONG."""
    logger.debug("ping conn_id=%s", conn_id)
    pong = Envelope(
        type=MessageType.PONG,
        request_id=envelope.request_id,
        payload={},
    )
    await hub.send(conn_id, pong.to_json())


def make_ping_handler(hub: Any, logger: logging.Logger):
    """Return a bound ping handler coroutine for use with MessageRouter."""
    async def _handler(conn_id: str, envelope: Envelope) -> None:
        await handle_ping(conn_id, envelope, hub, logger)
    return _handler
