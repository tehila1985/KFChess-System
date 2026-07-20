from __future__ import annotations

from engine.models.board import Board
from engine.models.piece import Piece
from engine.models.position import Position
from engine.config import GameConfig, DEFAULT_CONFIG
from engine.arbiter.motion import ActiveMotion, CompletedMotion
from engine.arbiter.collision_resolver import CollisionResolver

__all__ = ["ActiveMotion", "CompletedMotion", "RealTimeArbiter"]


class RealTimeArbiter:
    """
    Responsible for managing all concurrently active motions.

    Responsibilities:
    - Maintaining the ActiveMotion list
    - Advancing time (advance_time) and applying resolved results to the board
    - Blocking route conflicts (two pieces heading to the same column from the same direction)

    Collision resolution (head-to-head, airborne) is delegated to CollisionResolver.
    Has no knowledge of chess rules — that is RuleEngine's responsibility.
    """

    def __init__(self, board: Board, config: GameConfig = DEFAULT_CONFIG,
                 resolver: CollisionResolver = None):
        self._board        = board
        self._config       = config
        self._current_time = 0
        self._motions: list[ActiveMotion] = []
        self._cooldowns: dict[Position, int] = {}
        self._resolver     = resolver or CollisionResolver()

    @property
    def current_time(self) -> int:
        return self._current_time

    @property
    def active_motions(self) -> list[ActiveMotion]:
        return list(self._motions)

    @property
    def cooldowns(self) -> dict[Position, int]:
        return dict(self._cooldowns)

    def is_on_cooldown(self, pos: Position) -> bool:
        end_time = self._cooldowns.get(pos)
        return end_time is not None and end_time > self._current_time

    def start_motion(self, piece: Piece, src: Position, dst: Position, duration: int) -> None:
        """
        Starts a new motion.

        Checks for route conflict first — if another piece is already heading to the same
        column from the same direction, the motion is blocked (prevents two pieces on the same path).
        The piece is removed from src immediately (the board shows it as moving).
        """
        if self._route_conflicts(src, dst):
            return
        if self.is_on_cooldown(src):
            return
        self._board.set_piece(src, None)
        self._motions.append(ActiveMotion(piece, src, dst, self._current_time, duration, is_jump=False))

    def start_jump(self, pos: Position) -> None:
        """
        Starts a jump — the piece stays on the board but is marked as airborne.
        During the jump it can capture an enemy piece that arrives at the same square.
        """
        piece = self._board.get_piece(pos)
        if piece is None:
            return
        if self.is_on_cooldown(pos):
            return
        self._motions.append(ActiveMotion(piece, pos, pos, self._current_time, self._config.jump_duration_ms, is_jump=True))

    def advance_time(self, delta_ms: int) -> list[CompletedMotion]:
        """Advances the simulation clock and triggers resolution of completed motions."""
        self._current_time += delta_ms
        self._cooldowns = {
            pos: end_time for pos, end_time in self._cooldowns.items()
            if end_time > self._current_time
        }
        return self._resolve()

    def _route_conflicts(self, src: Position, dst: Position) -> bool:
        """
        Blocks a motion if another piece is already moving to the same destination column from the same direction.

        Goal: prevent two pieces from "racing" along the same path simultaneously.
        The check is on the destination column and movement direction (left/right).
        """
        for m in self._motions:
            if m.is_jump:
                continue
            if m.dst.col == dst.col and m.src.col != dst.col:
                if (src.col < dst.col) == (m.src.col < m.dst.col):
                    return True
        return False

    def _resolve(self) -> list[CompletedMotion]:
        """Collects completed motions, delegates collision resolution, then applies results to the board."""
        done = sorted(
            [m for m in self._motions if m.end_time <= self._current_time],
            key=lambda m: (m.start_time, self._motions.index(m)),
        )
        if not done:
            return []

        for m in done:
            self._motions.remove(m)

        loser_indices, captured_map = self._resolver.resolve(done)

        results: list[CompletedMotion] = []

        # airborne results — captured piece comes from captured_map
        for i, motion in enumerate(done):
            if not motion.is_jump:
                continue
            if i in captured_map:
                other = captured_map[i]
                results.append(CompletedMotion(
                    piece    = motion.piece,
                    src      = motion.src,
                    dst      = motion.dst,
                    captured = other.piece,
                ))

        # regular motions — place at destination and capture whatever is there
        for i, motion in enumerate(done):
            if i in loser_indices or motion.is_jump:
                continue
            captured = self._board.get_piece(motion.dst)
            self._board.set_piece(motion.dst, motion.piece)
            self._cooldowns[motion.dst] = self._current_time + self._config.cooldown_ms
            results.append(CompletedMotion(
                piece    = motion.piece,
                src      = motion.src,
                dst      = motion.dst,
                captured = captured,
            ))

        return results
