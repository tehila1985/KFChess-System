"""
room_service.py — manages chess rooms (create/join/spectate).

SRP: room lifecycle and role assignment only.
Uses RoomIdGenerator for ID creation (config-driven, no hardcoded charset).
Hands off to GameSessionFactory once two players are seated.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Optional

from server.directories.base import AbstractRoomRegistry
from server.directories.in_memory import InMemoryRoomRegistry
from server.domain.enums import RoomRole
from server.domain.player import Player
from server.domain.room import Room
from server.config_loader import Settings


class RoomIdGenerator:
    """
    Generates unique room IDs from the configured alphabet and length.

    SRP: ID generation only. Nothing else.
    Config-driven (id_length, id_alphabet) — no hardcoded values.
    """

    def __init__(self, settings: Settings) -> None:
        self._length = settings.room.id_length
        self._alphabet = settings.room.id_alphabet

    def generate(self) -> str:
        return "".join(random.choices(self._alphabet, k=self._length))


@dataclass(frozen=True)
class JoinResult:
    role: RoomRole
    room_id: str
    game_started: bool = False


class RoomService:
    """
    Manages room creation, joining, and game start.

    Room storage is delegated to an AbstractRoomRegistry (in-memory today,
    Redis-backed in Phase 1 of the cloud-scale migration — see
    .github/Server_Design_Implementation_Plan.md) so this class never touches
    a data structure directly.

    Constructor parameters (DI): settings, factory, hub, game_handler, logger, registry.
    """

    def __init__(
        self,
        settings: Settings,
        factory: Any,            # GameSessionFactory
        hub: Any,                # ConnectionHub
        game_handler: Any,       # GameHandler
        id_generator: RoomIdGenerator,
        logger: logging.Logger,
        registry: Optional[AbstractRoomRegistry] = None,
        allocator: Optional[Any] = None,     # GameAllocator — Phase 3, optional
        nats_client: Optional[Any] = None,   # for handing off to another shard
        own_shard_id: Optional[str] = None,
        redis_client: Optional[Any] = None,  # for conn:{conn_id}:shard routing hints
    ) -> None:
        self._factory = factory
        self._hub = hub
        self._game_handler = game_handler
        self._id_gen = id_generator
        self._log = logger
        self._rooms: AbstractRoomRegistry = registry if registry is not None else InMemoryRoomRegistry()
        self._allocator = allocator
        self._nats_client = nats_client
        self._own_shard_id = own_shard_id
        self._redis_client = redis_client

    # ── Public API ────────────────────────────────────────────────────

    def create_room(self, owner: Player) -> str:
        """
        Create a new room owned by the given player (White).

        Returns the room_id. Owner is assigned White.
        """
        room_id = self._id_gen.generate()
        # Ensure uniqueness (collision extremely unlikely but guarded)
        while self._rooms.exists(room_id):
            room_id = self._id_gen.generate()

        room = Room(room_id=room_id, owner=owner, white=owner)
        self._rooms.create(room)
        self._log.info("room_created room_id=%s owner=%s", room_id, owner.username)
        return room_id

    def join_room(self, room_id: str, player: Player) -> Optional[JoinResult]:
        """
        Join an existing room.

        Role assignment:
        - 1st joiner = owner (already White)
        - 2nd joiner = Black
        - 3rd+ = Viewer

        Returns JoinResult or None if room_id is invalid.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return None

        if room.black is None and room.white.conn_id != player.conn_id:
            # Second player → Black
            room.black = player
            role = RoomRole.BLACK
            self._log.info("room_joined room_id=%s user=%s role=black", room_id, player.username)
        else:
            # Viewer
            if player not in room.viewers:
                room.viewers.append(player)
            role = RoomRole.VIEWER
            self._log.info("room_joined room_id=%s user=%s role=viewer", room_id, player.username)

            # If the game is already running, subscribe this viewer directly —
            # start_game_if_ready() won't fire again for this room (it's a
            # one-shot, guarded by room.game_id), so this is the only way a
            # late-joining viewer gets onto the session's broadcast list.
            if room.game_id is not None:
                session = self._game_handler.get_session(room.game_id)
                if session is not None:
                    session.add_viewer(player.conn_id)

        self._rooms.save(room)
        return JoinResult(role=role, room_id=room_id, game_started=room.is_full())

    def get_room(self, room_id: str) -> Optional[Room]:
        """Return the Room by ID — never exposes internal storage."""
        return self._rooms.get(room_id)

    async def start_game_if_ready(self, room_id: str) -> bool:
        """
        Start the game when both player slots are filled.

        Returns True if a game was started.

        Phase 3 of .github/Server_Design_Implementation_Plan.md: if a
        GameAllocator is configured, ask it which Shard should run this
        game before constructing anything, and hand off over NATS if it
        isn't this one — same pattern as
        MatchmakingService._pair(). Known limitation of the hand-off path:
        a viewer joining this room *after* the game has already started
        would normally be attached directly via
        get_session(room.game_id).add_viewer(...) in join_room() above,
        but that session only exists in this shard's memory if the game
        was never handed off — a late viewer joining a handed-off room's
        game is not addressed by this phase (would need its own
        "add_viewer" cross-shard event) and is a documented gap, not a
        silent one.
        """
        import uuid
        from server.services.game_handoff import finalize_local_game, publish_create_game

        room = self._rooms.get(room_id)
        if room is None or not room.is_full() or room.game_id is not None:
            return False

        game_id = str(uuid.uuid4())
        viewer_conn_ids = [v.conn_id for v in room.viewers]
        target_shard = self._allocator.allocate(game_id) if self._allocator is not None else None

        if target_shard is not None and target_shard != self._own_shard_id:
            self._log.info("room_game_handoff room_id=%s game_id=%s target_shard=%s",
                           room_id, game_id, target_shard)
            await publish_create_game(
                self._nats_client, target_shard, room.white, room.black, game_id,
                room_id=room_id, viewer_conn_ids=viewer_conn_ids, send_match_found=False,
            )
            room.game_id = game_id
            self._rooms.save(room)
            return True

        await finalize_local_game(
            self._factory, self._game_handler, self._hub,
            room.white, room.black, game_id, room_id=room_id,
            viewer_conn_ids=viewer_conn_ids, send_match_found=False, logger=self._log,
            redis_client=self._redis_client, own_shard_id=self._own_shard_id,
        )
        room.game_id = game_id
        self._rooms.save(room)
        self._log.info("room_game_started room_id=%s game_id=%s", room_id, game_id)
        return True
