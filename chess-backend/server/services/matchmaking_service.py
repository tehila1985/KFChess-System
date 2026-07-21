"""
matchmaking_service.py — pairs players within ±ELO band, times out stragglers.

SRP: queue management only. Calls GameSessionFactory on a successful pairing.
Does NOT construct GameSession itself.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from server.domain.player import Player
from server.config_loader import Settings


@dataclass
class _QueueEntry:
    player: Player
    enqueued_at: float = field(default_factory=time.monotonic)


class MatchmakingService:
    """
    In-memory matchmaking queue.

    Responsibilities:
    - enqueue / dequeue players
    - background loop that pairs players within the ELO band or expires them
    - calls factory.create() + session.start() on a match (DRY: no game logic here)

    Constructor parameters (DI): settings, factory, hub, logger.
    """

    def __init__(
        self,
        settings: Settings,
        factory: Any,           # GameSessionFactory
        hub: Any,               # ConnectionHub
        game_handler: Any,      # GameHandler — to register the session
        logger: logging.Logger,
    ) -> None:
        self._match_range = settings.rating.match_range
        self._queue_timeout = settings.matchmaking.queue_timeout_seconds
        self._poll_interval = settings.matchmaking.poll_interval_seconds
        self._factory = factory
        self._hub = hub
        self._game_handler = game_handler
        self._log = logger
        self._queue: List[_QueueEntry] = []
        self._task: Optional[asyncio.Task] = None

    # ── Public API ────────────────────────────────────────────────────

    def enqueue(self, player: Player) -> None:
        """Add a player to the matchmaking queue."""
        # Prevent double-queueing the same connection
        if any(e.player.conn_id == player.conn_id for e in self._queue):
            return
        self._queue.append(_QueueEntry(player=player))
        self._log.info("matchmaking_enqueue user=%s elo=%d", player.username, player.elo)

    def dequeue(self, conn_id: str) -> None:
        """Remove a player from the queue (cancelled search)."""
        before = len(self._queue)
        self._queue = [e for e in self._queue if e.player.conn_id != conn_id]
        if len(self._queue) < before:
            self._log.info("matchmaking_dequeue conn_id=%s", conn_id)

    def queue_size(self) -> int:
        return len(self._queue)

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
        now = time.monotonic()
        matched: set[str] = set()

        # Try to pair each unmatched entry with the closest ELO opponent
        for i, entry_a in enumerate(self._queue):
            if entry_a.player.conn_id in matched:
                continue
            for entry_b in self._queue[i + 1 :]:
                if entry_b.player.conn_id in matched:
                    continue
                elo_diff = abs(entry_a.player.elo - entry_b.player.elo)
                if elo_diff <= self._match_range:
                    matched.add(entry_a.player.conn_id)
                    matched.add(entry_b.player.conn_id)
                    await self._pair(entry_a.player, entry_b.player)
                    break

        # Remove matched entries
        self._queue = [e for e in self._queue if e.player.conn_id not in matched]

        # Expire timed-out entries
        expired = [e for e in self._queue if (now - e.enqueued_at) >= self._queue_timeout]
        for e in expired:
            await self._expire(e.player)
        self._queue = [e for e in self._queue if e.player.conn_id not in {x.player.conn_id for x in expired}]

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
