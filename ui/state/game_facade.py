from __future__ import annotations

from dataclasses import dataclass

from engine.game_engine import GameEngine, MotionSummary, RequestMoveResult
from engine.models.position import Position
from ui.state.game_events import GameOver, MoveAccepted, MoveRejected, PieceArrived, PieceCaptured
from ui.state.outcome import ActionOutcome
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

    def get_legal_destinations(self, src: Position) -> tuple[Position, ...]:
        return self._engine.get_legal_destinations(src)

    def is_on_cooldown(self, pos: Position) -> bool:
        return self._engine.is_on_cooldown(pos)

    def is_game_over(self) -> bool:
        return self._engine.is_game_over()

    def request_move(self, src: Position, dst: Position) -> ActionOutcome:
        moving_piece = self._engine.get_piece_at(src)
        result = self._engine.request_move(src, dst)
        if result == RequestMoveResult.ACCEPTED:
            side = moving_piece.color if moving_piece is not None else "?"
            piece_type = moving_piece.type_code if moving_piece is not None else "?"
            at_ms = self._engine.current_time
            self._subject.publish(MoveAccepted(side=side, piece_type=piece_type, at_ms=at_ms, src=src, dst=dst))
            return ActionOutcome.ok()
        else:
            self._subject.publish(MoveRejected(src=src, dst=dst, reason=result))
            return ActionOutcome.fail(result)

    def request_jump(self, pos: Position) -> None:
        self._engine.request_jump(pos)

    def tick(self, delta_ms: int) -> None:
        before = self._freeze_active_motions()
        before_snapshot = self._engine.get_snapshot()
        self._engine.tick(delta_ms)
        after = self._freeze_active_motions()

        completed = before - after
        for motion in completed:
            piece = self._engine.get_piece_at(motion.dst)
            if piece is not None and piece.token == motion.token:
                self._subject.publish(
                    PieceArrived(
                        side=piece.color,
                        piece_type=piece.type_code,
                        src=motion.src,
                        dst=motion.dst,
                    )
                )

            # Capture must be detected from pre-tick destination occupancy.
            dst_cell_before = before_snapshot.grid[motion.dst.row][motion.dst.col]
            if dst_cell_before != "." and dst_cell_before[0] != motion.token[0]:
                self._subject.publish(
                    PieceCaptured(
                        captured_side=dst_cell_before[0],
                        captured_type=dst_cell_before[1],
                        at=motion.dst,
                    )
                )

        snapshot = self._engine.get_snapshot()
        if snapshot.game_over and not self._published_game_over:
            self._published_game_over = True
            self._subject.publish(GameOver(winner=snapshot.winner))

    def _freeze_active_motions(self) -> set[_FrozenMotion]:
        snap = self._engine.get_snapshot()
        return {_FrozenMotion.from_motion(motion) for motion in snap.active_motions}
