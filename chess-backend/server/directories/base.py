"""
base.py — abstract interfaces for the three pieces of ephemeral state that
move from in-process memory to Redis in Phase 1:

- AbstractConnectionDirectory: conn_id <-> websocket, conn_id <-> session_token
- AbstractMatchQueue: the matchmaking waiting line
- AbstractRoomRegistry: room_id -> Room lookup

Services (ConnectionHub already satisfies AbstractConnectionDirectory today;
MatchmakingService and RoomService are constructed with an
AbstractMatchQueue / AbstractRoomRegistry instance) depend only on these
interfaces, never on a concrete storage backend.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Set, Tuple

from server.domain.player import Player
from server.domain.room import Room


class AbstractConnectionDirectory(ABC):
    """Registry mapping connection_id <-> websocket and <-> session_token."""

    @abstractmethod
    def register(self, conn_id: str, websocket: Any) -> None: ...

    @abstractmethod
    def unregister(self, conn_id: str) -> None: ...

    @abstractmethod
    def get_conn_id_by_token(self, session_token: str) -> Optional[str]: ...

    @abstractmethod
    async def broadcast(self, conn_ids: Set[str], message: str) -> None: ...


class AbstractMatchQueue(ABC):
    """The matchmaking waiting line: enqueue/dequeue players, form pairs, expire stragglers."""

    @abstractmethod
    def enqueue(self, player: Player) -> None: ...

    @abstractmethod
    def dequeue(self, conn_id: str) -> None: ...

    @abstractmethod
    def size(self) -> int: ...

    @abstractmethod
    def pop_expired(self, timeout_seconds: float) -> List[Player]:
        """Remove and return every entry that has waited >= timeout_seconds."""
        ...

    @abstractmethod
    def pairs_within_range(self, match_range: int) -> List[Tuple[Player, Player]]:
        """Remove and return every pair of queued players within match_range ELO of each other."""
        ...


class AbstractRoomRegistry(ABC):
    """room_id -> Room storage: create, look up, persist mutations, check existence."""

    @abstractmethod
    def create(self, room: Room) -> None: ...

    @abstractmethod
    def get(self, room_id: str) -> Optional[Room]: ...

    @abstractmethod
    def exists(self, room_id: str) -> bool: ...

    @abstractmethod
    def save(self, room: Room) -> None:
        """Persist a mutation made to a Room previously returned by get().

        A no-op for an in-memory dict (the object is already shared), but a
        real write for a Redis-backed implementation — called explicitly so
        the in-memory implementation's behavior generalizes to Phase 1
        without callers needing to change.
        """
        ...
