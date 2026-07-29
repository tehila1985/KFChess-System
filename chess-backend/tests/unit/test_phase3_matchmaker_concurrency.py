"""
Phase 3 of .github/Server_Design_Implementation_Plan.md: proves the
concurrency-safety claim its own Definition of Done requires — two
Matchmaker replicas racing to pair the same two queued players must not
produce two games. RedisMatchQueue.pairs_within_range/pop_expired hold a
short Redis-backed lock around their read-then-remove critical section
specifically to make this true; this test is the regression net for that
lock, using real threads (not just sequential calls) so the race is real.

Requires a real Redis reachable at REDIS_TEST_URL. Skipped, not failed,
if unreachable.
"""
from __future__ import annotations

import os
import sys
import threading
import uuid

import pytest
import redis as redis_lib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.directories.redis_backed import RedisMatchQueue
from server.domain.player import Player

REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://localhost:6380/0")


def _redis_reachable() -> bool:
    try:
        client = redis_lib.Redis.from_url(REDIS_TEST_URL, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


REDIS_UP = _redis_reachable()
pytestmark = pytest.mark.skipif(not REDIS_UP, reason=f"redis not reachable at {REDIS_TEST_URL}")


def make_player(username, elo, conn_id):
    return Player(user_id=abs(hash(username)) % 1000, username=username, elo=elo,
                  conn_id=conn_id, session_token=f"tok_{username}")


def test_two_replicas_racing_never_double_pair():
    key = f"test:matchmaking:concurrency:{uuid.uuid4().hex}"
    client = redis_lib.Redis.from_url(REDIS_TEST_URL, decode_responses=True)

    # Two independent RedisMatchQueue instances (standing in for two
    # separate Matchmaker replica processes) sharing the same Redis key.
    replica_a = RedisMatchQueue(client, key=key)
    replica_b = RedisMatchQueue(client, key=key)

    replica_a.enqueue(make_player("alice", 1200, "c1"))
    replica_a.enqueue(make_player("bob", 1210, "c2"))
    assert replica_a.size() == 2

    results: list[list] = [None, None]
    barrier = threading.Barrier(2)

    def run(replica, slot):
        barrier.wait()  # start both threads' pairing pass at the same instant
        results[slot] = replica.pairs_within_range(match_range=50)

    t1 = threading.Thread(target=run, args=(replica_a, 0))
    t2 = threading.Thread(target=run, args=(replica_b, 1))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    total_pairs = len(results[0]) + len(results[1])
    assert total_pairs == 1, f"expected exactly one replica to win the pairing race, got {results}"
    assert replica_a.size() == 0  # both players removed from the shared queue, not left dangling


def test_many_replicas_racing_still_produce_exactly_one_pair():
    key = f"test:matchmaking:concurrency:{uuid.uuid4().hex}"
    client = redis_lib.Redis.from_url(REDIS_TEST_URL, decode_responses=True)

    seed = RedisMatchQueue(client, key=key)
    seed.enqueue(make_player("alice", 1200, "c1"))
    seed.enqueue(make_player("bob", 1210, "c2"))

    n = 8
    replicas = [RedisMatchQueue(client, key=key) for _ in range(n)]
    results = [None] * n
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()
        results[i] = replicas[i].pairs_within_range(match_range=50)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    total_pairs = sum(len(r) for r in results)
    assert total_pairs == 1, f"expected exactly one pair across {n} racing replicas, got {results}"
