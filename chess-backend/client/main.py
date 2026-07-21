"""
client/main.py — shell client entrypoint.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import os

# Add chess-backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from server.config_loader import load_settings
from server.logging_.logger_factory import LoggerFactory
from client.client_session import ClientSession
from client.shell_ui import ShellUI
from client.logging_.client_logger import ClientLogger


async def main():
    settings = load_settings()
    factory = LoggerFactory(
        level=settings.logging.level,
        rotate_max_bytes=settings.logging.rotate_max_bytes,
        rotate_backups=settings.logging.rotate_backups,
    )
    raw_logger = factory.get_client_logger(settings.logging.client_log_path)
    client_logger = ClientLogger(raw_logger)

    uri = f"ws://{settings.server.host}:{settings.server.port}"
    session = ClientSession(uri=uri, client_logger=client_logger)

    try:
        await session.connect()
    except Exception as exc:
        print(f"Cannot connect to server: {exc}")
        return

    # Start receive loop in background
    recv_task = asyncio.create_task(session.receive_loop())

    ui = ShellUI(session=session, client_logger=client_logger)
    try:
        await ui.run()
    finally:
        recv_task.cancel()
        await session.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
