"""
game_session.py — one instance per active game.

Wraps the existing chess engine (imported from engine/).
SRP: game state, move dispatch, disconnect handling, and end-game logic.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Set

# The existing chess engine lives at the project root (engine/)
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_root_dir = os.path.dirname(_backend_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from engine.game_engine import GameEngine, RequestMoveResult
from engine.models.board import Board
from engine.models.position import Position
from engine.rules.rule_engine import RuleEngine
from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.config import DEFAULT_CONFIG, WHITE as ENGINE_WHITE, BLACK as ENGINE_BLACK

from common.protocol.message_types import MessageType
from common.protocol.schemas import (
    Envelope, MoveAckPayload, MoveBroadcastPayload, GameEndPayload,
    OpponentDisconnectedPayload, GameStartPayload,
)
from server.domain.enums import GameResult, EndReason
from server.domain.player import Player
from server.repositories.base_repository import AbstractUserRepository, AbstractGameRepository
from server.services.rating_service import RatingService


# Standard starting board layout
_STARTING_BOARD = [
    "bR bN bB bQ bK bB bN bR",
    "bP bP bP bP bP bP bP bP",
    ".  .  .  .  .  .  .  .",
    ".  .  .  .  .  .  .  .",
    ".  .  .  .  .  .  .  .",
    ".  .  .  .  .  .  .  .",
    "wP wP wP wP wP wP wP wP",
    "wR wN wB wQ wK wB wN wR",
]


@dataclass(frozen=True)
class MoveResult:
    accepted: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class BoardStateDTO:
    """Read-only board state. Never exposes internal storage by reference."""
    grid: tuple  # tuple[tuple[str, ...], ...]
    game_over: bool
    winner: Optional[str]
    scores: tuple


class GameSession:
    """
    One active game between two players.

    Wraps GameEngine (the existing chess engine).
    Exposes only a narrow public API — internal state is never leaked.
    """

    def __init__(
        self,
        game_id: str,
        white: Player,
        black: Player,
        hub: Any,
        user_repo: AbstractUserRepository,
        game_repo: AbstractGameRepository,
        rating_service: RatingService,
        logger: logging.Logger,
        disconnect_grace_seconds: int = 20,
        countdown_tick_seconds: float = 1.0,
        room_id: Optional[str] = None,
    ) -> None:
        self._game_id = game_id
        self._white = white
        self._black = black
        self._hub = hub
        self._user_repo = user_repo
        self._game_repo = game_repo
        self._rating = rating_service
        self._log = logger
        self._disconnect_grace = disconnect_grace_seconds
        self._tick_seconds = countdown_tick_seconds
        self._room_id = room_id
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._ended = False

        # Track viewer conn_ids
        self._viewers: Set[str] = set()

        # Engine setup
        board = Board(_STARTING_BOARD)
        arbiter = RealTimeArbiter(board, DEFAULT_CONFIG)
        rule_engine = RuleEngine()
        self._engine = GameEngine(
            board=board,
            rule_engine=rule_engine,
            arbiter=arbiter,
            config=DEFAULT_CONFIG,
        )

        # Disconnect monitors (one per player slot): {conn_id: asyncio.Task}
        self._disconnect_tasks: Dict[str, asyncio.Task] = {}

    # ── Properties ────────────────────────────────────────────────────

    @property
    def game_id(self) -> str:
        return self._game_id

    @property
    def white(self) -> Player:
        return self._white

    @property
    def black(self) -> Player:
        return self._black

    # ── Viewers ───────────────────────────────────────────────────────

    def add_viewer(self, conn_id: str) -> None:
        self._viewers.add(conn_id)

    def remove_viewer(self, conn_id: str) -> None:
        self._viewers.discard(conn_id)

    # ── Public API ────────────────────────────────────────────────────

    def get_state(self) -> BoardStateDTO:
        """Return a read-only snapshot of the board — never raw internal state."""
        snap = self._engine.get_snapshot()
        return BoardStateDTO(
            grid=snap.grid,
            game_over=snap.game_over,
            winner=snap.winner,
            scores=snap.scores,
        )

    async def start(self) -> None:
        """Broadcast GAME_START to both players."""
        self._log.info("game_started game_id=%s white=%s black=%s",
                       self._game_id, self._white.username, self._black.username)
        for player, color in ((self._white, ENGINE_WHITE), (self._black, ENGINE_BLACK)):
            env = Envelope(
                type=MessageType.GAME_START,
                payload=GameStartPayload(
                    game_id=self._game_id,
                    color=color,
                    opponent=(self._black if color == ENGINE_WHITE else self._white).username,
                    room_id=self._room_id,
                ).model_dump(),
            )
            await self._hub.send(player.conn_id, env.to_json())

    async def apply_move(
        self, conn_id: str, src_row: int, src_col: int, dst_row: int, dst_col: int
    ) -> MoveResult:
        """
        Attempt to apply a move from the player at conn_id.

        Returns MoveResult(accepted=True/False, reason=...).
        Broadcasts move to both players and viewers on success.
        """
        if self._ended:
            return MoveResult(False, "game_over")

        player, color = self._player_and_color(conn_id)
        if player is None:
            return MoveResult(False, "not_a_player")

        src = Position(src_row, src_col)
        dst = Position(dst_row, dst_col)
        result = self._engine.request_move(src, dst)

        if result == RequestMoveResult.ACCEPTED:
            self._log.info("move_applied game_id=%s user=%s src=(%d,%d) dst=(%d,%d)",
                           self._game_id, player.username, src_row, src_col, dst_row, dst_col)
            await self._broadcast_move(color, src_row, src_col, dst_row, dst_col)

            # Tick engine to process immediate captures
            self._engine.tick(0)

            snapshot = self._engine.get_snapshot()
            if snapshot.game_over:
                winner_color = snapshot.winner
                winner = self._white if winner_color == ENGINE_WHITE else self._black
                loser = self._black if winner_color == ENGINE_WHITE else self._white
                game_result = (
                    GameResult.WHITE_WINS if winner_color == ENGINE_WHITE else GameResult.BLACK_WINS
                )
                await self.end_game(game_result, EndReason.CHECKMATE)

            return MoveResult(True)
        else:
            reason = result.name.lower()
            self._log.warning("move_rejected game_id=%s user=%s reason=%s",
                              self._game_id, player.username if player else "?", reason)
            return MoveResult(False, reason)

    async def handle_disconnect(self, conn_id: str) -> None:
        """Start a countdown for the disconnected player."""
        if self._ended:
            return
        player, _ = self._player_and_color(conn_id)
        if player is None:
            return

        self._log.warning("disconnect_detected game_id=%s user=%s",
                          self._game_id, player.username)

        # Cancel any existing monitor for this conn
        await self._cancel_disconnect_task(conn_id)

        task = asyncio.create_task(
            self._run_countdown(player, conn_id)
        )
        self._disconnect_tasks[conn_id] = task

    async def handle_reconnect(self, old_conn_id: str, new_conn_id: str) -> None:
        """Cancel the countdown if the player reconnects within the grace period."""
        if await self._cancel_disconnect_task(old_conn_id):
            self._log.info("reconnect game_id=%s old_conn=%s new_conn=%s",
                           self._game_id, old_conn_id, new_conn_id)
            # Update player connection id
            if self._white.conn_id == old_conn_id:
                object.__setattr__(self._white, 'conn_id', new_conn_id)
            elif self._black.conn_id == old_conn_id:
                object.__setattr__(self._black, 'conn_id', new_conn_id)

    async def end_game(self, result: GameResult, reason: EndReason) -> None:
        """
        End the game: update ratings, persist, broadcast GAME_END.

        Called at most once — guarded by self._ended.
        """
        if self._ended:
            return
        self._ended = True

        # Cancel any pending countdown tasks
        for task in self._disconnect_tasks.values():
            task.cancel()
        self._disconnect_tasks.clear()

        white_elo_before = self._white.elo
        black_elo_before = self._black.elo

        new_white_elo, new_black_elo = self._rating.update_ratings(
            white_elo_before, black_elo_before, result
        )

        # Persist ELO updates
        self._user_repo.update_elo(self._white.user_id, new_white_elo)
        self._user_repo.update_elo(self._black.user_id, new_black_elo)

        ended_at = datetime.now(timezone.utc).isoformat()

        # Persist game record
        self._game_repo.record_game(
            white_user_id=self._white.user_id,
            black_user_id=self._black.user_id,
            result=result.value,
            end_reason=reason.value,
            white_elo_before=white_elo_before,
            black_elo_before=black_elo_before,
            white_elo_after=new_white_elo,
            black_elo_after=new_black_elo,
            room_id=self._room_id,
            started_at=self._started_at,
            ended_at=ended_at,
        )

        self._log.info(
            "game_ended game_id=%s result=%s reason=%s "
            "white_elo=%d->%d black_elo=%d->%d",
            self._game_id, result.value, reason.value,
            white_elo_before, new_white_elo,
            black_elo_before, new_black_elo,
        )

        # Broadcast GAME_END
        payload = GameEndPayload(
            result=result.value,
            reason=reason.value,
            white_elo_before=white_elo_before,
            black_elo_before=black_elo_before,
            white_elo_after=new_white_elo,
            black_elo_after=new_black_elo,
        ).model_dump()

        all_conns = {self._white.conn_id, self._black.conn_id} | self._viewers
        env = Envelope(type=MessageType.GAME_END, payload=payload)
        await self._hub.broadcast(all_conns, env.to_json())

    # ── Internal helpers ─────────────────────────────────────────────

    def _player_and_color(self, conn_id: str):
        if conn_id == self._white.conn_id:
            return self._white, ENGINE_WHITE
        if conn_id == self._black.conn_id:
            return self._black, ENGINE_BLACK
        return None, None

    async def _broadcast_move(
        self, color: str, src_row: int, src_col: int, dst_row: int, dst_col: int
    ) -> None:
        payload = MoveBroadcastPayload(
            src_row=src_row, src_col=src_col,
            dst_row=dst_row, dst_col=dst_col,
            color=color,
        ).model_dump()
        env = Envelope(type=MessageType.MOVE_BROADCAST, payload=payload)
        all_conns = {self._white.conn_id, self._black.conn_id} | self._viewers
        await self._hub.broadcast(all_conns, env.to_json())

    async def _run_countdown(self, player: Player, conn_id: str) -> None:
        """Count down and auto-resign if player doesn't reconnect."""
        from common.protocol.schemas import DisconnectCountdownTickPayload

        seconds = self._disconnect_grace
        other_conn = (
            self._black.conn_id
            if conn_id == self._white.conn_id
            else self._white.conn_id
        )

        # Notify opponent
        notif = Envelope(
            type=MessageType.OPPONENT_DISCONNECTED,
            payload=OpponentDisconnectedPayload(username=player.username).model_dump(),
        )
        conns_to_notify = {other_conn} | self._viewers
        await self._hub.broadcast(conns_to_notify, notif.to_json())

        try:
            while seconds > 0:
                tick = Envelope(
                    type=MessageType.DISCONNECT_COUNTDOWN_TICK,
                    payload=DisconnectCountdownTickPayload(seconds_left=seconds).model_dump(),
                )
                await self._hub.broadcast(conns_to_notify, tick.to_json())
                self._log.info("countdown_tick game_id=%s user=%s seconds_left=%d",
                               self._game_id, player.username, seconds)
                await asyncio.sleep(self._tick_seconds)
                seconds -= 1

            # Countdown elapsed → auto-resign
            self._log.warning("auto_resign game_id=%s user=%s", self._game_id, player.username)
            result = (
                GameResult.BLACK_WINS
                if conn_id == self._white.conn_id
                else GameResult.WHITE_WINS
            )
            await self.end_game(result, EndReason.DISCONNECT_TIMEOUT)

        except asyncio.CancelledError:
            pass  # reconnect cancelled the timer

    async def _cancel_disconnect_task(self, conn_id: str) -> bool:
        task = self._disconnect_tasks.pop(conn_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return True
        return False
