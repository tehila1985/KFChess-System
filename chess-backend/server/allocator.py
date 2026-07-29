"""
allocator.py — Game Allocator (Phase 2 of .github/Server_Design_Implementation_Plan.md).

Phase 2 has exactly one Shard, so "allocate" always resolves to it — this is
deliberately the simplest possible thing that writes game:{game_id} -> shard_id
to Redis, so the *interface* Phase 3's real placement-by-load allocator will
have already exists and is exercised end-to-end.
"""
from __future__ import annotations

from typing import Any


class GameAllocator:
    def __init__(self, redis_client: Any, shard_id: str) -> None:
        self._redis = redis_client
        self._shard_id = shard_id

    def allocate(self, game_id: str) -> str:
        """Record which shard owns game_id and return that shard_id.

        Phase 2: trivially always self._shard_id (one shard exists).
        Phase 3 replaces this method's body with real load-aware placement —
        every caller (GameSessionFactory) stays unchanged.
        """
        self._redis.set(f"game:{game_id}", self._shard_id)
        return self._shard_id

    def shard_for(self, game_id: str) -> str:
        """Look up which shard owns an existing game_id (used by the Gateway
        to route MOVE/RESIGN to the right shard.{id}.inbound subject)."""
        value = self._redis.get(f"game:{game_id}")
        if value is None:
            return self._shard_id
        return value.decode() if isinstance(value, bytes) else value
