from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from engine.models.board import Board
from engine.models.piece import Piece
from engine.models.position import Position
from engine.config import GameConfig, DEFAULT_CONFIG


@dataclass(frozen=True)
class ActiveMotion:
    """
    An active motion that has not yet completed.

    is_jump=True: the piece "flies" above the board and lands on the same square (src == dst).
    During a jump the piece remains on the board (not removed from the grid).
    In a regular motion the piece is removed from src at the moment of start_motion.
    """
    piece:      Piece
    src:        Position
    dst:        Position
    start_time: int
    duration:   int
    is_jump:    bool = False

    @property
    def end_time(self) -> int:
        return self.start_time + self.duration


@dataclass(frozen=True)
class CompletedMotion:
    """Result of a completed motion — returned to GameEngine for capture/promotion handling."""
    piece:    Piece
    src:      Position
    dst:      Position
    captured: Optional[Piece]  # the captured piece, or None


class RealTimeArbiter:
    """
    Responsible for managing all concurrently active motions.

    Responsibilities:
    - Maintaining the ActiveMotion list
    - Advancing time (advance_time) and resolving completed motions
    - Detecting head-to-head collisions (whoever started first wins)
    - Handling jumps (a jumping piece captures an arriving enemy)
    - Blocking route conflicts (two pieces heading to the same column from the same direction)

    Has no knowledge of chess rules — that is RuleEngine's responsibility.
    """

    def __init__(self, board: Board, config: GameConfig = DEFAULT_CONFIG):
        self._board        = board
        self._config       = config
        self._current_time = 0
        self._motions: list[ActiveMotion] = []

    @property
    def current_time(self) -> int:
        return self._current_time

    @property
    def active_motions(self) -> list[ActiveMotion]:
        return list(self._motions)

    def start_motion(self, piece: Piece, src: Position, dst: Position, duration: int) -> None:
        """
        Starts a new motion.

        Checks for route conflict first — if another piece is already heading to the same
        column from the same direction, the motion is blocked (prevents two pieces on the same path).
        The piece is removed from src immediately (the board shows it as moving).
        """
        if self._route_conflicts(src, dst):
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
        self._motions.append(ActiveMotion(piece, pos, pos, self._current_time, self._config.jump_duration_ms, is_jump=True))

    def advance_time(self, delta_ms: int) -> list[CompletedMotion]:
        """Advances the simulation clock and triggers resolution of completed motions."""
        self._current_time += delta_ms
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
        """
        Resolves all motions that have reached end_time <= current_time.

        Resolution order:
        1. Sort by start_time (whoever started first)
        2. head-to-head: two pieces that swapped positions — the later one loses
        3. jumps: a jumping piece captures an enemy arriving at the same square
        4. regular motions: place the piece at destination, capture whatever is there
        """
        done = sorted(
            [m for m in self._motions if m.end_time <= self._current_time],
            key=lambda m: (m.start_time, self._motions.index(m)),
        )
        if not done:
            return []

        for m in done:
            self._motions.remove(m)

        # Phase 1: head-to-head — whoever started later loses
        loser_indices: set[int] = set()
        for i, a in enumerate(done):
            for j, b in enumerate(done):
                if i >= j or a.is_jump or b.is_jump:
                    continue
                if a.dst == b.src and a.src == b.dst:
                    if b.start_time < a.start_time:
                        loser_indices.add(i)
                    else:
                        loser_indices.add(j)

        results: list[CompletedMotion] = []

        # Phase 2: jumps — a jumping piece captures an enemy arriving at the same square
        airborne = {i for i, m in enumerate(done) if m.is_jump}
        for i, motion in enumerate(done):
            if i not in airborne:
                continue
            for j, other in enumerate(done):
                if j in loser_indices or other.is_jump or other.dst != motion.src:
                    continue
                # the arriving piece is captured by the jumper
                loser_indices.add(j)
                results.append(CompletedMotion(
                    piece    = motion.piece,
                    src      = motion.src,
                    dst      = motion.dst,
                    captured = other.piece,
                ))

        # Phase 3: regular motions — place at destination and capture whatever is there
        for i, motion in enumerate(done):
            if i in loser_indices or motion.is_jump:
                continue

            captured = self._board.get_piece(motion.dst)
            self._board.set_piece(motion.dst, motion.piece)

            results.append(CompletedMotion(
                piece    = motion.piece,
                src      = motion.src,
                dst      = motion.dst,
                captured = captured,
            ))

        return results
