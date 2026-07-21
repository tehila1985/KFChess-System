"""
main.py — server entrypoint.

Wires up the DI container, starts the ConnectionHub, and runs the WebSocket server.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import websockets

from server.config_loader import load_settings
from server.connection_hub import ConnectionHub
from server.message_router import MessageRouter
from server.handlers.system_handler import make_ping_handler
from server.logging_.server_logger import build_server_logger
from server.logging_.logger_factory import LoggerFactory
from common.protocol.message_types import MessageType


async def serve(settings=None, router: MessageRouter = None, hub: ConnectionHub = None,
                server_logger=None):
    """
    Main server coroutine. Creates all objects and starts listening.

    Parameters are injectable for testing.
    """
    if settings is None:
        settings = load_settings()

    if server_logger is None:
        server_logger = build_server_logger(settings)

    raw_logger = logging.getLogger("chess.server")

    if hub is None:
        hub = ConnectionHub(logger=raw_logger)

    if router is None:
        router = MessageRouter(hub=hub, logger=raw_logger)
        router.register(MessageType.PING, make_ping_handler(hub, raw_logger))

    async def connection_handler(websocket):
        conn_id = str(uuid.uuid4())
        remote = str(websocket.remote_address)
        hub.register(conn_id, websocket)
        server_logger.connection_opened(conn_id, remote)

        try:
            async for raw_message in websocket:
                await router.route(conn_id, raw_message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            hub.unregister(conn_id)
            server_logger.connection_closed(conn_id, remote)

    host = settings.server.host
    port = settings.server.port
    raw_logger.info("Server starting on %s:%s", host, port)

    async with websockets.serve(connection_handler, host, port):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(serve())
