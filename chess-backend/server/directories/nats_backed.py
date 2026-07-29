"""
nats_backed.py — Phase 2 of .github/Server_Design_Implementation_Plan.md.

NatsPublishingConnectionDirectory is the Shard-side substitution for
ConnectionHub/RedisConnectionDirectory: the Shard process never holds a
live websocket (that lives in the Gateway process), so send()/broadcast()
publish an outbound envelope over NATS instead of writing to a socket.
This is the one real code change GameSession's hub dependency needed for
the Gateway/Shard split — a substitution, not a rewrite, because
GameSession only ever calls hub.send()/broadcast()/broadcast_to_tokens().

Session-token <-> conn_id lookup is unchanged from Phase 1 (still Redis,
still needs to survive a freshly restarted Gateway); conn_id "liveness"
(is_connected/all_conn_ids) is tracked from the "connected"/"disconnected"
lifecycle events the Gateway publishes to this shard's inbound subject —
see shard/main.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional, Set

from server.directories.base import AbstractConnectionDirectory


class NatsPublishingConnectionDirectory(AbstractConnectionDirectory):
    def __init__(
        self,
        nats_client: Any,
        redis_client: Any,
        shard_id: str,
        session_key_prefix: str = "session",
        ttl_seconds: int = 86400,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._nc = nats_client
        self._redis = redis_client
        self._outbound_subject = f"shard.{shard_id}.outbound"
        self._prefix = session_key_prefix
        self._ttl = ttl_seconds
        self._known_conn_ids: Set[str] = set()
        self._conn_to_token: Dict[str, str] = {}
        self._disconnect_callbacks: list[Callable[[str], None]] = []
        self._log = logger or logging.getLogger(__name__)

    def _key(self, session_token: str) -> str:
        return f"{self._prefix}:{session_token}"

    # ── Registration — driven by "connected"/"disconnected" NATS events ──

    def register(self, conn_id: str, websocket: Any = None) -> None:
        # websocket is unused here on purpose: the Shard never holds one.
        self._known_conn_ids.add(conn_id)

    def unregister(self, conn_id: str) -> None:
        self._known_conn_ids.discard(conn_id)
        self._conn_to_token.pop(conn_id, None)
        for cb in self._disconnect_callbacks:
            try:
                cb(conn_id)
            except Exception:
                self._log.exception("disconnect_callback_error conn_id=%s", conn_id)

    def associate_token(self, conn_id: str, session_token: str) -> None:
        old_conn = self._redis.get(self._key(session_token))
        if isinstance(old_conn, bytes):
            old_conn = old_conn.decode()
        if old_conn is not None:
            self._conn_to_token.pop(old_conn, None)
        self._redis.set(self._key(session_token), conn_id, ex=self._ttl)
        self._conn_to_token[conn_id] = session_token

    # ── Lookup ───────────────────────────────────────────────────────

    def get_conn_id_by_token(self, session_token: str) -> Optional[str]:
        value = self._redis.get(self._key(session_token))
        return value.decode() if isinstance(value, bytes) else value

    def get_token_by_conn_id(self, conn_id: str) -> Optional[str]:
        return self._conn_to_token.get(conn_id)

    def is_connected(self, conn_id: str) -> bool:
        return conn_id in self._known_conn_ids

    def all_conn_ids(self) -> Set[str]:
        return set(self._known_conn_ids)

    # ── Sending — publish to NATS, Gateway does the real socket write ──

    async def send(self, conn_id: str, message: str) -> bool:
        payload = json.dumps({"conn_id": conn_id, "message": message}).encode()
        await self._nc.publish(self._outbound_subject, payload)
        return True

    async def send_to_token(self, session_token: str, message: str) -> bool:
        conn_id = self.get_conn_id_by_token(session_token)
        if conn_id is None:
            return False
        return await self.send(conn_id, message)

    async def broadcast(self, conn_ids: Set[str], message: str) -> None:
        if not conn_ids:
            return
        await asyncio.gather(
            *(self.send(cid, message) for cid in conn_ids),
            return_exceptions=True,
        )

    async def broadcast_to_tokens(self, tokens: Set[str], message: str) -> None:
        if not tokens:
            return
        await asyncio.gather(
            *(self.send_to_token(t, message) for t in tokens if t),
            return_exceptions=True,
        )

    # ── Callbacks ────────────────────────────────────────────────────

    def on_disconnect(self, callback: Callable[[str], None]) -> None:
        self._disconnect_callbacks.append(callback)
