"""
client/gui_main.py — networked GUI client entrypoint.

Reuses the existing local chess GUI (ui/) for rendering, driven over the
network instead of a local engine. See client/gui/ for the scene stack.
"""
from __future__ import annotations

import os
import sys

# Add chess-backend to path (for server.*/client.*/common.* imports).
_backend_dir = os.path.dirname(os.path.dirname(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
# Add the repo root to path (for ui.*/engine.* imports).
_root_dir = os.path.dirname(_backend_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from server.config_loader import load_settings
from server.logging_.logger_factory import LoggerFactory
from client.logging_.client_logger import ClientLogger
from client.gui.network_client import NetworkClient
from client.gui.app import App


def main() -> None:
    settings = load_settings()
    factory = LoggerFactory(
        level=settings.logging.level,
        rotate_max_bytes=settings.logging.rotate_max_bytes,
        rotate_backups=settings.logging.rotate_backups,
    )
    raw_logger = factory.get_client_logger(settings.logging.client_log_path)
    client_logger = ClientLogger(raw_logger)

    # "0.0.0.0" is a bind-all address for the server, not a connectable
    # target — translate it to loopback for the client's own connection.
    connect_host = "127.0.0.1" if settings.server.host == "0.0.0.0" else settings.server.host
    uri = f"ws://{connect_host}:{settings.server.port}"

    network = NetworkClient(uri=uri, client_logger=client_logger)
    try:
        network.start()
    except Exception as exc:
        print(f"Cannot connect to server: {exc}")
        return

    App(network).run()


if __name__ == "__main__":
    main()
