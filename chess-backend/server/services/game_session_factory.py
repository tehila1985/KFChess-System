"""
game_session_factory.py — the ONLY place that constructs a GameSession.

Both MatchmakingService and RoomService call this factory.
This is the DRY seam that prevents divergent game-start logic.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from server.domain.player import Player
from server.repositories.base_repository import AbstractUserRepository, AbstractGameRepository
from server.services.game_session import GameSession
from server.services.rating_service import RatingService
from server.config_loader import Settings


class GameSessionFactory:
    """
    Creates GameSession instances.

    Constructor parameters (DI): all dependencies that GameSession needs.
    """

    def __init__(
        self,
        hub: Any,
        user_repo: AbstractUserRepository,
        game_repo: AbstractGameRepository,
        rating_service: RatingService,
        settings: Settings,
        logger: logging.Logger,
    ) -> None:
        self._hub = hub
        self._user_repo = user_repo
        self._game_repo = game_repo
        self._rating = rating_service
        self._settings = settings
        self._log = logger

    def create(
        self,
        white: Player,
        black: Player,
        room_id: Optional[str] = None,
        game_id: Optional[str] = None,
    ) -> GameSession:
        """
        Create and return a new GameSession for the given players.

        Args:
            white: The player who will play White.
            black: The player who will play Black.
            room_id: Optional room ID (None for matchmaking games).
            game_id: Explicit game_id (Phase 3 of
                .github/Server_Design_Implementation_Plan.md: the caller
                allocates a shard for this game_id *before* deciding whether
                to construct it locally or hand it off to another Shard
                process — see server/services/game_handoff.py — so the id
                has to exist before this call, not be invented by it).
                Auto-generated if omitted, for callers that don't need it
                (single-shard / monolith usage, unchanged from Phase 0-2).

        Returns:
            A new GameSession instance (not yet started — caller must await .start()).
        """
        if game_id is None:
            game_id = str(uuid.uuid4())
        self._log.info(
            "game_session_creating game_id=%s white=%s black=%s room_id=%s",
            game_id, white.username, black.username, room_id,
        )
        return GameSession(
            game_id=game_id,
            white=white,
            black=black,
            hub=self._hub,
            user_repo=self._user_repo,
            game_repo=self._game_repo,
            rating_service=self._rating,
            logger=self._log,
            disconnect_grace_seconds=self._settings.game.disconnect_grace_seconds,
            countdown_tick_seconds=self._settings.game.countdown_tick_seconds,
            room_id=room_id,
        )
