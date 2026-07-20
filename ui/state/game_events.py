from __future__ import annotations

from dataclasses import dataclass

from engine.game_engine import RequestMoveResult
from engine.models.position import Position


@dataclass(frozen=True)
class MoveAccepted:
    side: str
    piece_type: str
    at_ms: int
    src: Position
    dst: Position


@dataclass(frozen=True)
class MoveRejected:
    src: Position
    dst: Position
    reason: RequestMoveResult


@dataclass(frozen=True)
class PieceArrived:
    side: str
    piece_type: str
    src: Position
    dst: Position


@dataclass(frozen=True)
class PieceCaptured:
    captured_side: str
    captured_type: str
    points: int
    at: Position


@dataclass(frozen=True)
class GameOver:
    winner: str | None
