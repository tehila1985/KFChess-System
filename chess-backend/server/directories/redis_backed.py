"""
redis_backed.py — Phase 1 of .github/Server_Design_Implementation_Plan.md.

Redis-backed implementations of the Phase 0 interfaces (server/directories/base.py).
Still runs inside a single process (Phase 1's whole point is proving the Redis
integration in isolation from any network-topology change) — only the
*storage* moves, so these classes are drop-in replacements for
InMemoryMatchQueue / InMemoryRoomRegistry / ConnectionHub behind the same
constructor-injected interface.

Key shapes match Server_Design.md §1 Q2:
- "session:{token}"       -> conn_id, TTL = auth.session_token_ttl_seconds
- "room:{room_id}"        -> JSON-serialized Room, TTL refreshed on save()
- "matchmaking:queue"     -> ELO-scored sorted set (member = JSON player, score = elo)
- "matchmaking:queue:ts:{conn_id}" -> enqueued_at, used by pop_expired()
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from server.directories.base import (
    AbstractConnectionDirectory,
    AbstractMatchQueue,
    AbstractRoomRegistry,
)
from server.domain.player import Player
from server.domain.room import Room


def _s(value: Any) -> Optional[str]:
    """Decode a redis-py return value to str regardless of decode_responses."""
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else value


def _player_to_json(player: Player) -> str:
    return json.dumps({
        "user_id": player.user_id,
        "username": player.username,
        "elo": player.elo,
        "conn_id": player.conn_id,
        "session_token": player.session_token,
    })


def _player_from_json(raw: str) -> Player:
    d = json.loads(raw)
    return Player(**d)


def _room_to_json(room: Room) -> str:
    def player_or_none(p: Optional[Player]) -> Optional[dict]:
        return None if p is None else json.loads(_player_to_json(p))

    return json.dumps({
        "room_id": room.room_id,
        "owner": player_or_none(room.owner),
        "white": player_or_none(room.white),
        "black": player_or_none(room.black),
        "viewers": [player_or_none(v) for v in room.viewers],
        "game_id": room.game_id,
    })


def _room_from_json(raw: str) -> Room:
    d = json.loads(raw)

    def to_player(pd: Optional[dict]) -> Optional[Player]:
        return None if pd is None else Player(**pd)

    return Room(
        room_id=d["room_id"],
        owner=to_player(d["owner"]),
        white=to_player(d["white"]),
        black=to_player(d["black"]),
        viewers=[to_player(v) for v in d["viewers"]],
        game_id=d["game_id"],
    )


class RedisMatchQueue(AbstractMatchQueue):
    """ELO-scored sorted set, per Server_Design.md §1 Q2."""

    def __init__(self, redis_client: Any, key: str = "matchmaking:queue") -> None:
        self._redis = redis_client
        self._key = key
        self._ts_prefix = f"{key}:ts:"

    def enqueue(self, player: Player) -> None:
        if self._redis.zscore(self._key, player.conn_id) is not None:
            return
        self._redis.zadd(self._key, {player.conn_id: player.elo})
        self._redis.hset(f"{self._key}:players", player.conn_id, _player_to_json(player))
        self._redis.set(f"{self._ts_prefix}{player.conn_id}", str(time.monotonic()))

    def dequeue(self, conn_id: str) -> None:
        self._redis.zrem(self._key, conn_id)
        self._redis.hdel(f"{self._key}:players", conn_id)
        self._redis.delete(f"{self._ts_prefix}{conn_id}")

    def size(self) -> int:
        return self._redis.zcard(self._key)

    def _all_players(self) -> List[Player]:
        # zrange preserves ELO-ascending order — cheapest deterministic scan order.
        conn_ids = self._redis.zrange(self._key, 0, -1)
        players: List[Player] = []
        for conn_id in conn_ids:
            raw = _s(self._redis.hget(f"{self._key}:players", conn_id))
            if raw is not None:
                players.append(_player_from_json(raw))
        return players

    def pop_expired(self, timeout_seconds: float) -> List[Player]:
        now = time.monotonic()
        expired: List[Player] = []
        for player in self._all_players():
            ts_raw = _s(self._redis.get(f"{self._ts_prefix}{player.conn_id}"))
            enqueued_at = float(ts_raw) if ts_raw is not None else now
            if (now - enqueued_at) >= timeout_seconds:
                expired.append(player)
        for player in expired:
            self.dequeue(player.conn_id)
        return expired

    def pairs_within_range(self, match_range: int) -> List[Tuple[Player, Player]]:
        players = self._all_players()  # ELO-ascending
        matched: set[str] = set()
        pairs: List[Tuple[Player, Player]] = []
        for i, a in enumerate(players):
            if a.conn_id in matched:
                continue
            for b in players[i + 1 :]:
                if b.conn_id in matched:
                    continue
                if abs(a.elo - b.elo) <= match_range:
                    matched.add(a.conn_id)
                    matched.add(b.conn_id)
                    pairs.append((a, b))
                    break
        for conn_id in matched:
            self.dequeue(conn_id)
        return pairs


class RedisRoomRegistry(AbstractRoomRegistry):
    """"room:{room_id}" -> JSON Room, per Server_Design.md §1 Q2."""

    def __init__(self, redis_client: Any, key_prefix: str = "room", ttl_seconds: int = 86400) -> None:
        self._redis = redis_client
        self._prefix = key_prefix
        self._ttl = ttl_seconds

    def _key(self, room_id: str) -> str:
        return f"{self._prefix}:{room_id}"

    def create(self, room: Room) -> None:
        self._redis.set(self._key(room.room_id), _room_to_json(room), ex=self._ttl)

    def get(self, room_id: str) -> Optional[Room]:
        raw = _s(self._redis.get(self._key(room_id)))
        return None if raw is None else _room_from_json(raw)

    def exists(self, room_id: str) -> bool:
        return bool(self._redis.exists(self._key(room_id)))

    def save(self, room: Room) -> None:
        self._redis.set(self._key(room.room_id), _room_to_json(room), ex=self._ttl)


class RedisConnectionDirectory(AbstractConnectionDirectory):
    """
    conn_id -> websocket stays local (a live socket can't be serialized into
    Redis), but session_token -> conn_id lives in "session:{token}" with a
    TTL, so a freshly started Gateway process (Phase 2) can resolve a
    reconnecting client's token without any gateway-local state.
    """

    def __init__(
        self,
        redis_client: Any,
        key_prefix: str = "session",
        ttl_seconds: int = 86400,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._redis = redis_client
        self._prefix = key_prefix
        self._ttl = ttl_seconds
        self._connections: Dict[str, Any] = {}
        self._conn_to_token: Dict[str, str] = {}
        self._disconnect_callbacks: list = []
        self._log = logger or logging.getLogger(__name__)

    def _key(self, session_token: str) -> str:
        return f"{self._prefix}:{session_token}"

    # ── Registration ─────────────────────────────────────────────────

    def register(self, conn_id: str, websocket: Any) -> None:
        self._connections[conn_id] = websocket

    def unregister(self, conn_id: str) -> None:
        self._connections.pop(conn_id, None)
        self._conn_to_token.pop(conn_id, None)
        for cb in self._disconnect_callbacks:
            try:
                cb(conn_id)
            except Exception:
                self._log.exception("disconnect_callback_error conn_id=%s", conn_id)

    def associate_token(self, conn_id: str, session_token: str) -> None:
        old_conn = _s(self._redis.get(self._key(session_token)))
        if old_conn is not None:
            self._conn_to_token.pop(old_conn, None)
        self._redis.set(self._key(session_token), conn_id, ex=self._ttl)
        self._conn_to_token[conn_id] = session_token

    # ── Lookup ───────────────────────────────────────────────────────

    def get_websocket(self, conn_id: str) -> Optional[Any]:
        return self._connections.get(conn_id)

    def get_conn_id_by_token(self, session_token: str) -> Optional[str]:
        return _s(self._redis.get(self._key(session_token)))

    def get_token_by_conn_id(self, conn_id: str) -> Optional[str]:
        return self._conn_to_token.get(conn_id)

    def is_connected(self, conn_id: str) -> bool:
        return conn_id in self._connections

    def all_conn_ids(self) -> Set[str]:
        return set(self._connections.keys())

    # ── Sending ──────────────────────────────────────────────────────

    async def send(self, conn_id: str, message: str) -> bool:
        ws = self._connections.get(conn_id)
        if ws is None:
            return False
        try:
            await ws.send(message)
            return True
        except Exception as exc:
            self._log.warning("hub_send_error conn_id=%s exc=%s", conn_id, exc)
            return False

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

    def on_disconnect(self, callback) -> None:
        self._disconnect_callbacks.append(callback)
