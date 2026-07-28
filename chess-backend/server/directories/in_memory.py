"""
in_memory.py — today's storage, expressed against the Phase 0 interfaces.

InMemoryMatchQueue and InMemoryRoomRegistry are behavior-identical
extractions of logic that used to live directly inside MatchmakingService
and RoomService. ConnectionHub (server/connection_hub.py) already satisfies
AbstractConnectionDirectory structurally and declares it explicitly there.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from server.directories.base import AbstractMatchQueue, AbstractRoomRegistry
from server.domain.player import Player
from server.domain.room import Room


@dataclass
class _QueueEntry:
    player: Player
    enqueued_at: float = field(default_factory=time.monotonic)


class InMemoryMatchQueue(AbstractMatchQueue):
    def __init__(self) -> None:
        self._queue: List[_QueueEntry] = []

    def enqueue(self, player: Player) -> None:
        if any(e.player.conn_id == player.conn_id for e in self._queue):
            return
        self._queue.append(_QueueEntry(player=player))

    def dequeue(self, conn_id: str) -> None:
        self._queue = [e for e in self._queue if e.player.conn_id != conn_id]

    def size(self) -> int:
        return len(self._queue)

    def pop_expired(self, timeout_seconds: float) -> List[Player]:
        now = time.monotonic()
        expired = [e for e in self._queue if (now - e.enqueued_at) >= timeout_seconds]
        expired_ids = {e.player.conn_id for e in expired}
        self._queue = [e for e in self._queue if e.player.conn_id not in expired_ids]
        return [e.player for e in expired]

    def pairs_within_range(self, match_range: int) -> List[Tuple[Player, Player]]:
        matched: set[str] = set()
        pairs: List[Tuple[Player, Player]] = []
        for i, entry_a in enumerate(self._queue):
            if entry_a.player.conn_id in matched:
                continue
            for entry_b in self._queue[i + 1 :]:
                if entry_b.player.conn_id in matched:
                    continue
                if abs(entry_a.player.elo - entry_b.player.elo) <= match_range:
                    matched.add(entry_a.player.conn_id)
                    matched.add(entry_b.player.conn_id)
                    pairs.append((entry_a.player, entry_b.player))
                    break
        self._queue = [e for e in self._queue if e.player.conn_id not in matched]
        return pairs


class InMemoryRoomRegistry(AbstractRoomRegistry):
    def __init__(self) -> None:
        self._rooms: Dict[str, Room] = {}

    def create(self, room: Room) -> None:
        self._rooms[room.room_id] = room

    def get(self, room_id: str) -> Optional[Room]:
        return self._rooms.get(room_id)

    def exists(self, room_id: str) -> bool:
        return room_id in self._rooms

    def save(self, room: Room) -> None:
        # Object is already shared in-process; mutations are visible for free.
        pass
