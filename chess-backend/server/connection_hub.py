"""
connection_hub.py — tracks live sockets ↔ session tokens.

SRP: connection registry only. Knows nothing about games, rooms, or auth.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Set


class ConnectionHub:
    """
    Registry mapping connection_id → websocket.

    Also tracks optional session_token → connection_id for authenticated users.

    No module accesses internal dicts directly — everything goes through methods.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._connections: Dict[str, Any] = {}          # conn_id → websocket
        self._conn_to_token: Dict[str, str] = {}        # conn_id → session_token
        self._token_to_conn: Dict[str, str] = {}        # session_token → conn_id
        self._disconnect_callbacks: list[Callable[[str], None]] = []
        self._log = logger or logging.getLogger(__name__)

    # ── Registration ─────────────────────────────────────────────────

    def register(self, conn_id: str, websocket: Any) -> None:
        """Register a new connection."""
        self._connections[conn_id] = websocket
        self._log.debug("hub_register conn_id=%s", conn_id)

    def unregister(self, conn_id: str) -> None:
        """Remove a connection and clean up any associated session token."""
        self._connections.pop(conn_id, None)
        token = self._conn_to_token.pop(conn_id, None)
        if token is not None:
            self._token_to_conn.pop(token, None)
        self._log.debug("hub_unregister conn_id=%s", conn_id)
        for cb in self._disconnect_callbacks:
            try:
                cb(conn_id)
            except Exception:
                self._log.exception("disconnect_callback_error conn_id=%s", conn_id)

    def associate_token(self, conn_id: str, session_token: str) -> None:
        """Associate an authenticated session token with a connection."""
        # Remove any previous association for this token
        old_conn = self._token_to_conn.pop(session_token, None)
        if old_conn is not None:
            self._conn_to_token.pop(old_conn, None)
        self._conn_to_token[conn_id] = session_token
        self._token_to_conn[session_token] = conn_id

    # ── Lookup ───────────────────────────────────────────────────────

    def get_websocket(self, conn_id: str) -> Optional[Any]:
        return self._connections.get(conn_id)

    def get_conn_id_by_token(self, session_token: str) -> Optional[str]:
        return self._token_to_conn.get(session_token)

    def get_token_by_conn_id(self, conn_id: str) -> Optional[str]:
        return self._conn_to_token.get(conn_id)

    def is_connected(self, conn_id: str) -> bool:
        return conn_id in self._connections

    def all_conn_ids(self) -> Set[str]:
        return set(self._connections.keys())

    # ── Sending ──────────────────────────────────────────────────────

    async def send(self, conn_id: str, message: str) -> bool:
        """
        Send a message to a connection by conn_id.

        Returns True if sent, False if the connection is not registered.
        """
        ws = self._connections.get(conn_id)
        if ws is None:
            self._log.debug("hub_send_miss conn_id=%s", conn_id)
            return False
        try:
            await ws.send(message)
            return True
        except Exception as exc:
            self._log.warning("hub_send_error conn_id=%s exc=%s", conn_id, exc)
            return False

    async def broadcast(self, conn_ids: Set[str], message: str) -> None:
        """Send a message to multiple connections concurrently."""
        if not conn_ids:
            return
        await asyncio.gather(
            *(self.send(cid, message) for cid in conn_ids),
            return_exceptions=True,
        )

    # ── Callbacks ────────────────────────────────────────────────────

    def on_disconnect(self, callback: Callable[[str], None]) -> None:
        """Register a callback invoked when a connection is unregistered."""
        self._disconnect_callbacks.append(callback)
