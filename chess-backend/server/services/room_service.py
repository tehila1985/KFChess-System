"""
room_service.py — manages chess rooms (create/join/spectate).

SRP: room lifecycle and role assignment only.
Uses RoomIdGenerator for ID creation (config-driven, no hardcoded charset).
Hands off to GameSessionFactory once two players are seated.
"""
from __future__ import annotations

import logging
import random
import string
from dataclasses import dataclass
from typing import Any, Dict, Optional

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

    Constructor parameters (DI): settings, factory, hub, game_handler, logger.
    """

    def __init__(
        self,
        settings: Settings,
        factory: Any,            # GameSessionFactory
        hub: Any,                # ConnectionHub
        game_handler: Any,       # GameHandler
        id_generator: RoomIdGenerator,
        logger: logging.Logger,
    ) -> None:
        self._factory = factory
        self._hub = hub
        self._game_handler = game_handler
        self._id_gen = id_generator
        self._log = logger
        self._rooms: Dict[str, Room] = {}

    # ── Public API ────────────────────────────────────────────────────

    def create_room(self, owner: Player) -> str:
        """
        Create a new room owned by the given player (White).

        Returns the room_id. Owner is assigned White.
        """
        room_id = self._id_gen.generate()
        # Ensure uniqueness (collision extremely unlikely but guarded)
        while room_id in self._rooms:
            room_id = self._id_gen.generate()

        room = Room(room_id=room_id, owner=owner, white=owner)
        self._rooms[room_id] = room
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

        return JoinResult(role=role, room_id=room_id, game_started=room.is_full())

    def get_room(self, room_id: str) -> Optional[Room]:
        """Return the Room by ID — never exposes internal dict."""
        return self._rooms.get(room_id)

    async def start_game_if_ready(self, room_id: str) -> bool:
        """
        Start the game when both player slots are filled.

        Returns True if a game was started.
        """
        room = self._rooms.get(room_id)
        if room is None or not room.is_full():
            return False

        session = self._factory.create(
            white=room.white,
            black=room.black,
            room_id=room_id,
        )
        # Register viewers as spectators on the session
        for viewer in room.viewers:
            session.add_viewer(viewer.conn_id)

        self._game_handler.register_session(session)
        room.game_id = session.game_id
        await session.start()
        self._log.info("room_game_started room_id=%s game_id=%s", room_id, session.game_id)
        return True
