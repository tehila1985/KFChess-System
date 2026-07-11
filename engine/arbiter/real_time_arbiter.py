from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from engine.models.board import Board
from engine.models.piece import Piece
from engine.models.position import Position
from engine.config import JUMP_DURATION_MS


@dataclass(frozen=True)
class ActiveMotion:
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
    piece:    Piece
    src:      Position
    dst:      Position
    captured: Optional[Piece]


class RealTimeArbiter:
    def __init__(self, board: Board):
        self._board        = board
        self._current_time = 0
        self._motions: list[ActiveMotion] = []

    @property
    def current_time(self) -> int:
        return self._current_time

    @property
    def active_motions(self) -> list[ActiveMotion]:
        return list(self._motions)

    def start_motion(self, piece: Piece, src: Position, dst: Position, duration: int) -> None:
        # בדוק route conflict: אם כלי אחר כבר הולך לאותה עמודה מאותו כיוון
        if self._route_conflicts(src, dst):
            return
        self._board.set_piece(src, None)
        self._motions.append(ActiveMotion(piece, src, dst, self._current_time, duration, is_jump=False))

    def start_jump(self, pos: Position) -> None:
        piece = self._board.get_piece(pos)
        if piece is None:
            return
        self._motions.append(ActiveMotion(piece, pos, pos, self._current_time, JUMP_DURATION_MS, is_jump=True))

    def advance_time(self, delta_ms: int) -> list[CompletedMotion]:
        self._current_time += delta_ms
        return self._resolve()

    def _route_conflicts(self, src: Position, dst: Position) -> bool:
        """חסום תנועה אם כלי אחר כבר הולך לאותה עמודה יעד מאותו כיוון."""
        for m in self._motions:
            if m.is_jump:
                continue
            if m.dst.col == dst.col and m.src.col != dst.col:
                if (src.col < dst.col) == (m.src.col < m.dst.col):
                    return True
        return False

    def _resolve(self) -> list[CompletedMotion]:
        done = sorted(
            [m for m in self._motions if m.end_time <= self._current_time],
            key=lambda m: (m.start_time, self._motions.index(m)),
        )
        if not done:
            return []

        for m in done:
            self._motions.remove(m)

        # head-to-head: שני כלים שהחליפו מקומות
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

        # שלב 1: טפל בקפיצות - קופץ אוכל כלי מגיע
        airborne = {i for i, m in enumerate(done) if m.is_jump}
        for i, motion in enumerate(done):
            if i not in airborne:
                continue
            # חפש כלי שמגיע אל הקופץ
            for j, other in enumerate(done):
                if j in loser_indices or other.is_jump or other.dst != motion.src:
                    continue
                # הכלי המגיע נתפס על ידי הקופץ
                captured_piece = self._board.get_piece(other.src) or other.piece
                loser_indices.add(j)
                scorer_color = other.piece.color  # הקופץ מנצח
                results.append(CompletedMotion(
                    piece    = motion.piece,
                    src      = motion.src,
                    dst      = motion.dst,
                    captured = other.piece,
                ))

        # שלב 2: טפל בתנועות רגילות
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
