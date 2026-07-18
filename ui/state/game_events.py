from __future__ import annotations

from dataclasses import dataclass

from engine.game_engine import RequestMoveResult
from engine.models.piece import Piece
from engine.models.position import Position


@dataclass(frozen=True)
class MoveAccepted:
    src: Position
    dst: Position


@dataclass(frozen=True)
class MoveRejected:
    src: Position
    dst: Position
    reason: RequestMoveResult


@dataclass(frozen=True)
class PieceArrived:
    piece: Piece
    src: Position
    dst: Position


@dataclass(frozen=True)
class PieceCaptured:
    captured: Piece
    at: Position


@dataclass(frozen=True)
class GameOver:
    winner: str | None
