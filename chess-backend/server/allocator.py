"""
allocator.py — Game Allocator (Phase 2 → Phase 3 of
.github/Server_Design_Implementation_Plan.md).

Phase 2: exactly one shard exists, so "allocate" always resolves to it.
Phase 3: real placement — picks the least-loaded of the shards currently
reporting a live heartbeat, verified locally with N real Shard processes
(no live Kubernetes cluster needed; see the plan doc's Phase 3 "reality
check").
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


class GameAllocator:
    def __init__(
        self,
        redis_client: Any,
        shard_id: str,
        known_shards_key: str = "shards:known",
        heartbeat_prefix: str = "shard",
    ) -> None:
        self._redis = redis_client
        self._shard_id = shard_id
        self._known_key = known_shards_key
        self._hb_prefix = heartbeat_prefix

    # ── Self-registration + heartbeat (called by the Shard process itself) ──

    def register_self(self) -> None:
        """Add this shard to the known-shards set. Called once at startup."""
        self._redis.sadd(self._known_key, self._shard_id)

    def report_load(self, active_game_count: int, ttl_seconds: int = 5) -> None:
        """
        Refresh this shard's heartbeat with its current load. TTL makes this
        a dead-man's switch too (see shard/main.py's heartbeat_loop): a
        hard-killed shard's key simply expires, so `_alive_loads` below
        never has to distinguish "never reported" from "stopped reporting."
        """
        key = f"{self._hb_prefix}:{self._shard_id}:heartbeat"
        self._redis.set(key, json.dumps({"load": active_game_count}), ex=ttl_seconds)

    # ── Placement ────────────────────────────────────────────────────────

    def _known_shard_ids(self) -> set:
        members = self._redis.smembers(self._known_key)
        return {m.decode() if isinstance(m, bytes) else m for m in members}

    def _alive_loads(self) -> Dict[str, int]:
        loads: Dict[str, int] = {}
        for shard_id in self._known_shard_ids():
            raw = self._redis.get(f"{self._hb_prefix}:{shard_id}:heartbeat")
            if raw is None:
                continue  # heartbeat expired — treat as dead, not zero-load
            raw = raw.decode() if isinstance(raw, bytes) else raw
            try:
                loads[shard_id] = json.loads(raw).get("load", 0)
            except (ValueError, TypeError):
                loads[shard_id] = 0
        return loads

    def allocate(self, game_id: str) -> str:
        """
        Pick the least-loaded shard with a live heartbeat, record
        game:{game_id} -> shard_id, and return it.

        Falls back to this allocator's own shard_id if no shard has ever
        reported a heartbeat (e.g. Phase 2 usage, or a unit test that never
        called register_self()/report_load()) — this is exactly Phase 2's
        "one shard, always resolves to it" behavior, preserved as the
        degenerate case rather than a special branch.
        """
        loads = self._alive_loads()
        if not loads:
            chosen = self._shard_id
        else:
            # sorted() before min() so ties break on shard_id, deterministically —
            # matters for the "which shard actually got it" tests.
            chosen = min(sorted(loads), key=lambda sid: loads[sid])
        self._redis.set(f"game:{game_id}", chosen)
        return chosen

    def shard_for(self, game_id: str) -> Optional[str]:
        """Look up which shard owns an existing game_id."""
        value = self._redis.get(f"game:{game_id}")
        if value is None:
            return self._shard_id
        return value.decode() if isinstance(value, bytes) else value
