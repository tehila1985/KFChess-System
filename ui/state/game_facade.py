from __future__ import annotations

from dataclasses import dataclass

from engine.game_engine import GameEngine, MotionSummary, RequestMoveResult
from engine.models.position import Position
from ui.state.game_events import GameOver, MoveAccepted, MoveRejected, PieceArrived, PieceCaptured
from ui.state.observer import EventBus, Subject


@dataclass(frozen=True)
class _FrozenMotion:
    """Immutable motion record to diff state across ticks safely."""

    token: str
    src: Position
    dst: Position

    @classmethod
    def from_motion(cls, motion: MotionSummary) -> "_FrozenMotion":
        return cls(token=motion.piece.token, src=motion.src, dst=motion.dst)


class GameFacade:
    """
    Thin UI-facing facade over GameEngine.

    Responsibilities:
    - delegate all game logic to the server-side engine
    - publish observer events for UI subscribers
    - avoid snapshot diffing of full boards by tracking active motions only
    """

    def __init__(self, engine: GameEngine, subject: Subject | None = None) -> None:
        self._engine = engine
        self._subject = subject or EventBus()
        self._published_game_over = False

    @property
    def subject(self) -> Subject:
        return self._subject

    def get_piece_at(self, pos: Position):
        return self._engine.get_piece_at(pos)

    def get_snapshot(self):
        return self._engine.get_snapshot()

    def request_move(self, src: Position, dst: Position) -> RequestMoveResult:
        result = self._engine.request_move(src, dst)
        if result == RequestMoveResult.ACCEPTED:
            self._subject.publish(MoveAccepted(src=src, dst=dst))
        else:
            self._subject.publish(MoveRejected(src=src, dst=dst, reason=result))
        return result

    def request_jump(self, pos: Position) -> None:
        self._engine.request_jump(pos)

    def tick(self, delta_ms: int) -> None:
        before = self._freeze_active_motions()
        self._engine.tick(delta_ms)
        after = self._freeze_active_motions()

        completed = before - after
        snapshot = self._engine.get_snapshot()
        for motion in completed:
            piece = self._engine.get_piece_at(motion.dst)
            if piece is not None and piece.token == motion.token:
                self._subject.publish(PieceArrived(piece=piece, src=motion.src, dst=motion.dst))
            else:
                captured_piece = self._find_piece_by_token(snapshot.grid, motion.token)
                if captured_piece is None:
                    # token not present after completion means the moving piece was removed.
                    continue

            # If something was on destination before completion, engine already accounted for scoring.
            # We emit capture based on occupancy change at destination.
            if self._was_capture(before_motion=motion, current_grid=snapshot.grid):
                captured = self._captured_piece_at_destination(motion.dst, motion.token, snapshot.grid)
                if captured is not None:
                    self._subject.publish(PieceCaptured(captured=captured, at=motion.dst))

        if snapshot.game_over and not self._published_game_over:
            self._published_game_over = True
            self._subject.publish(GameOver(winner=snapshot.winner))

    def _freeze_active_motions(self) -> set[_FrozenMotion]:
        snap = self._engine.get_snapshot()
        return {_FrozenMotion.from_motion(motion) for motion in snap.active_motions}

    @staticmethod
    def _find_piece_by_token(grid: tuple, token: str):
        for row in grid:
            for cell in row:
                if cell == token:
                    return None
        return None

    @staticmethod
    def _was_capture(before_motion: _FrozenMotion, current_grid: tuple) -> bool:
        dst = before_motion.dst
        return current_grid[dst.row][dst.col] != "." and current_grid[dst.row][dst.col] != before_motion.token

    @staticmethod
    def _captured_piece_at_destination(dst: Position, moving_token: str, grid: tuple):
        cell = grid[dst.row][dst.col]
        if cell in (".", moving_token):
            return None
        color = cell[0]
        type_code = cell[1]
        from engine.models.piece import Piece

        return Piece(color=color, type_code=type_code)
