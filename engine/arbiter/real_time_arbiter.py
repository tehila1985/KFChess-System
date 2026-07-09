from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from engine.models.board import Board
from engine.models.piece import Piece
from engine.models.position import Position


@dataclass(frozen=True)
class ActiveMotion:
    piece:      Piece
    src:        Position
    dst:        Position
    start_time: int
    duration:   int

    @property
    def end_time(self) -> int:
        return self.start_time + self.duration


@dataclass(frozen=True)
class CompletedMotion:
    piece:    Piece
    src:      Position
    dst:      Position
    captured: Optional[Piece]   # None when the destination was empty


class RealTimeArbiter:
    """
    Owns the board and is the sole authority that moves pieces on it.

    Time is purely logical — no sleep, no wall-clock reads.
    Callers drive time forward with advance_time(delta_ms).
    """

    def __init__(self, board: Board):
        self._board        = board
        self._current_time = 0
        self._motions:  list[ActiveMotion] = []

    # ── public read-only access ────────────────────────────────────────

    @property
    def current_time(self) -> int:
        return self._current_time

    @property
    def active_motions(self) -> list[ActiveMotion]:
        return list(self._motions)

    # ── commands ───────────────────────────────────────────────────────

    def start_motion(self, piece: Piece, src: Position, dst: Position, duration: int) -> None:
        """
        Register a new in-flight motion.
        The piece is considered 'in transit' from src to dst.
        The source square is cleared immediately so no other motion
        can claim it; the destination is committed on arrival.
        """
        self._board.set_piece(src, None)
        self._motions.append(
            ActiveMotion(piece, src, dst, self._current_time, duration)
        )

    def advance_time(self, delta_ms: int) -> list[CompletedMotion]:
        """
        Advance the logical clock by delta_ms and resolve every motion
        whose end_time has been reached.

        Returns a list of CompletedMotion — one entry per piece that
        landed this tick, in start_time order (earliest first).
        No time.sleep, no I/O.
        """
        self._current_time += delta_ms
        return self._resolve()

    # ── internals ─────────────────────────────────────────────────────

    def _resolve(self) -> list[CompletedMotion]:
        done = sorted(
            [m for m in self._motions if m.end_time <= self._current_time],
            key=lambda m: (m.start_time, self._motions.index(m)),
        )
        if not done:
            return []

        for m in done:
            self._motions.remove(m)

        # Detect head-to-head: two pieces that swapped src/dst and both
        # completed this tick.  The one that started earlier wins; the
        # loser is simply dropped (its source was already cleared in
        # start_motion, so it vanishes from the board).
        loser_indices: set[int] = set()
        for i, a in enumerate(done):
            for j, b in enumerate(done):
                if i >= j:
                    continue
                if a.dst == b.src and a.src == b.dst:
                    # head-to-head — later starter loses
                    if b.start_time < a.start_time:
                        loser_indices.add(i)
                    else:
                        loser_indices.add(j)

        results: list[CompletedMotion] = []
        for i, motion in enumerate(done):
            if i in loser_indices:
                # Piece is lost in transit — board already cleared at src
                continue

            captured = self._board.get_piece(motion.dst)

            # Capture on arrival: whatever sits at dst is taken
            self._board.set_piece(motion.dst, motion.piece)

            results.append(CompletedMotion(
                piece    = motion.piece,
                src      = motion.src,
                dst      = motion.dst,
                captured = captured,
            ))

        return results
