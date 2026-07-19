from __future__ import annotations

import sys
from pathlib import Path


_SERVER_DIR = Path(__file__).resolve().parent.parent.parent / "server"


def ensure_server_path() -> None:
    """Add server directory to sys.path if present and not already set."""
    if _SERVER_DIR.exists():
        candidate = str(_SERVER_DIR)
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
