from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from server.models.piece import Piece
from server.models.position import Position


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
