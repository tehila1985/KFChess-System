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
        allocator: Optional[Any] = None,     # GameAllocator — Phase 3, optional
        nats_client: Optional[Any] = None,   # for handing off to another shard
        own_shard_id: Optional[str] = None,
        redis_client: Optional[Any] = None,  # for conn:{conn_id}:shard routing hints
    ) -> None:
        self._match_range = settings.rating.match_range
        self._queue_timeout = settings.matchmaking.queue_timeout_seconds
        self._poll_interval = settings.matchmaking.poll_interval_seconds
        self._factory = factory
        self._hub = hub
        self._game_handler = game_handler
        self._log = logger
        self._queue: AbstractMatchQueue = queue if queue is not None else InMemoryMatchQueue()
        self._allocator = allocator
        self._nats_client = nats_client
        self._own_shard_id = own_shard_id
        self._redis_client = redis_client
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
        """
        Pair two players: first enqueued = White.

        Phase 3 of .github/Server_Design_Implementation_Plan.md: if a
        GameAllocator is configured, ask it which Shard should run this
        game *before* constructing anything. If that's some other Shard,
        hand off over NATS instead of creating the session here — this
        Shard's own matchmaking loop won the pairing race, but that
        doesn't mean it should also host the game.
        """
        import uuid
        from server.services.game_handoff import finalize_local_game, publish_create_game

        self._log.info("matchmaking_match white=%s black=%s", first.username, second.username)

        game_id = str(uuid.uuid4())
        target_shard = self._allocator.allocate(game_id) if self._allocator is not None else None

        if target_shard is not None and target_shard != self._own_shard_id:
            self._log.info("matchmaking_handoff game_id=%s target_shard=%s", game_id, target_shard)
            await publish_create_game(
                self._nats_client, target_shard, first, second, game_id, send_match_found=True,
            )
            return

        await finalize_local_game(
            self._factory, self._game_handler, self._hub,
            first, second, game_id, send_match_found=True, logger=self._log,
            redis_client=self._redis_client, own_shard_id=self._own_shard_id,
        )

    async def _expire(self, player: Player) -> None:
        from common.protocol.message_types import MessageType
        from common.protocol.schemas import Envelope, PlayTimeoutPayload

        self._log.info("matchmaking_timeout user=%s", player.username)
        env = Envelope(
            type=MessageType.PLAY_TIMEOUT,
            payload=PlayTimeoutPayload().model_dump(),
        )
        await self._hub.send(player.conn_id, env.to_json())
