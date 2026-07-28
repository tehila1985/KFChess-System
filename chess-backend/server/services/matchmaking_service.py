"""
matchmaking_service.py — pairs players within ±ELO band, times out stragglers.

SRP: queue management only. Calls GameSessionFactory on a successful pairing.
Does NOT construct GameSession itself.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from server.directories.base import AbstractMatchQueue
from server.directories.in_memory import InMemoryMatchQueue
from server.domain.player import Player
from server.config_loader import Settings


class MatchmakingService:
    """
    Matchmaking queue.

    Responsibilities:
    - enqueue / dequeue players
    - background loop that pairs players within the ELO band or expires them
    - calls factory.create() + session.start() on a match (DRY: no game logic here)

    Queue storage is delegated to an AbstractMatchQueue (in-memory today,
    Redis-backed in Phase 1 of the cloud-scale migration — see
    .github/Server_Design_Implementation_Plan.md) so this class never touches
    a data structure directly.

    Constructor parameters (DI): settings, factory, hub, logger, queue.
    """

    def __init__(
        self,
        settings: Settings,
        factory: Any,           # GameSessionFactory
        hub: Any,               # ConnectionHub
        game_handler: Any,      # GameHandler — to register the session
        logger: logging.Logger,
        queue: Optional[AbstractMatchQueue] = None,
    ) -> None:
        self._match_range = settings.rating.match_range
        self._queue_timeout = settings.matchmaking.queue_timeout_seconds
        self._poll_interval = settings.matchmaking.poll_interval_seconds
        self._factory = factory
        self._hub = hub
        self._game_handler = game_handler
        self._log = logger
        self._queue: AbstractMatchQueue = queue if queue is not None else InMemoryMatchQueue()
        self._task: Optional[asyncio.Task] = None

    # ── Public API ────────────────────────────────────────────────────

    def enqueue(self, player: Player) -> None:
        """Add a player to the matchmaking queue."""
        before = self._queue.size()
        self._queue.enqueue(player)
        if self._queue.size() > before:
            self._log.info("matchmaking_enqueue user=%s elo=%d", player.username, player.elo)

    def dequeue(self, conn_id: str) -> None:
        """Remove a player from the queue (cancelled search)."""
        before = self._queue.size()
        self._queue.dequeue(conn_id)
        if self._queue.size() < before:
            self._log.info("matchmaking_dequeue conn_id=%s", conn_id)

    def queue_size(self) -> int:
        return self._queue.size()

    def start_background_loop(self) -> None:
        """Start the polling task. Called once from server startup."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    # ── Internal ──────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Background tick: pair matches and expire timeouts."""
        try:
            while True:
                await asyncio.sleep(self._poll_interval)
                await self._tick()
        except asyncio.CancelledError:
            pass

    async def _tick(self) -> None:
        """One poll cycle: try to form pairs, then expire stale entries."""
        for first, second in self._queue.pairs_within_range(self._match_range):
            await self._pair(first, second)

        for player in self._queue.pop_expired(self._queue_timeout):
            await self._expire(player)

    async def _pair(self, first: Player, second: Player) -> None:
        """Pair two players: first enqueued = White."""
        from common.protocol.message_types import MessageType
        from common.protocol.schemas import Envelope, PlayMatchFoundPayload

        self._log.info("matchmaking_match white=%s black=%s", first.username, second.username)

        session = self._factory.create(white=first, black=second)
        self._game_handler.register_session(session)

        # Notify both
        for player, color in ((first, "w"), (second, "b")):
            opponent = second if color == "w" else first
            env = Envelope(
                type=MessageType.PLAY_MATCH_FOUND,
                payload=PlayMatchFoundPayload(
                    opponent=opponent.username,
                    color=color,
                    game_id=session.game_id,
                ).model_dump(),
            )
            await self._hub.send(player.conn_id, env.to_json())

        await session.start()

    async def _expire(self, player: Player) -> None:
        from common.protocol.message_types import MessageType
        from common.protocol.schemas import Envelope, PlayTimeoutPayload

        self._log.info("matchmaking_timeout user=%s", player.username)
        env = Envelope(
            type=MessageType.PLAY_TIMEOUT,
            payload=PlayTimeoutPayload().model_dump(),
        )
        await self._hub.send(player.conn_id, env.to_json())
