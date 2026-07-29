"""
Phase 3 of .github/Server_Design_Implementation_Plan.md: GameAllocator's
real least-loaded placement, once shards have registered themselves and
are reporting a heartbeat/load — as opposed to Phase 2's degenerate
"always resolves to the only shard" case (still covered in
test_phase2_gateway_shard.py, unmodified by this).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.allocator import GameAllocator


class FakeRedis:
    def __init__(self):
        self.store: dict = {}
        self.sets: dict = {}

    def set(self, key, value, ex=None):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def sadd(self, key, member):
        self.sets.setdefault(key, set()).add(member)

    def smembers(self, key):
        return self.sets.get(key, set())


def make_allocators(redis_client, shard_ids):
    allocators = {sid: GameAllocator(redis_client, shard_id=sid) for sid in shard_ids}
    for a in allocators.values():
        a.register_self()
    return allocators


class TestGameAllocatorPlacement:
    def test_picks_least_loaded_known_shard(self):
        redis_client = FakeRedis()
        allocators = make_allocators(redis_client, ["shard-a", "shard-b", "shard-c"])
        allocators["shard-a"].report_load(5)
        allocators["shard-b"].report_load(1)
        allocators["shard-c"].report_load(3)

        chosen = allocators["shard-a"].allocate("game-1")
        assert chosen == "shard-b"
        assert allocators["shard-a"].shard_for("game-1") == "shard-b"

    def test_ties_break_deterministically_by_shard_id(self):
        redis_client = FakeRedis()
        allocators = make_allocators(redis_client, ["shard-z", "shard-a"])
        allocators["shard-z"].report_load(2)
        allocators["shard-a"].report_load(2)

        chosen = allocators["shard-z"].allocate("game-1")
        assert chosen == "shard-a"  # alphabetically first among equal loads

    def test_expired_heartbeat_is_treated_as_dead_not_zero_load(self):
        redis_client = FakeRedis()
        allocators = make_allocators(redis_client, ["shard-a", "shard-b"])
        allocators["shard-a"].report_load(10)
        # shard-b registered itself but never reported a heartbeat (or it
        # expired) — must not be treated as "load 0, pick me."
        chosen = allocators["shard-a"].allocate("game-1")
        assert chosen == "shard-a"

    def test_no_known_shards_falls_back_to_self(self):
        redis_client = FakeRedis()
        allocator = GameAllocator(redis_client, shard_id="shard-solo")
        # Never called register_self()/report_load() — Phase 2 usage.
        assert allocator.allocate("game-1") == "shard-solo"
