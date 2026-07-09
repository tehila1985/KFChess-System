from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from engine.models.board import Board
from engine.models.move import Move
from engine.models.piece import Piece
from engine.models.position import Position
from engine.rules.rule_engine import MoveStatus, RuleEngine
from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.config import WHITE, BLACK, KING, MOVE_DURATION_MS


# ── Result enum returned to the controller ────────────────────────────

class RequestMoveResult(Enum):
    ACCEPTED             = auto()
    GAME_OVER            = auto()   # move rejected — game already finished
    PIECE_BUSY           = auto()   # piece is already in motion
    OUTSIDE_BOARD        = auto()
    EMPTY_SOURCE         = auto()
    FRIENDLY_DESTINATION = auto()
    ILLEGAL_PIECE_MOVE   = auto()


_STATUS_MAP: dict[MoveStatus, RequestMoveResult] = {
    MoveStatus.OK:                   RequestMoveResult.ACCEPTED,
    MoveStatus.OUTSIDE_BOARD:        RequestMoveResult.OUTSIDE_BOARD,
    MoveStatus.EMPTY_SOURCE:         RequestMoveResult.EMPTY_SOURCE,
    MoveStatus.FRIENDLY_DESTINATION: RequestMoveResult.FRIENDLY_DESTINATION,
    MoveStatus.ILLEGAL_PIECE_MOVE:   RequestMoveResult.ILLEGAL_PIECE_MOVE,
}


# ── Read-only snapshot DTO ─────────────────────────────────────────────

@dataclass(frozen=True)
class MotionSummary:
    piece:      Piece
    src:        Position
    dst:        Position
    start_time: int
    end_time:   int


@dataclass(frozen=True)
class GameSnapshot:
    grid:           tuple           # tuple[tuple[str, ...], ...]  — raw tokens
    scores:         dict            # {color: numeric_score}
    game_over:      bool
    winner:         Optional[str]   # 'w', 'b', or None
    active_motions: tuple           # tuple[MotionSummary, ...]


# ── GameEngine ─────────────────────────────────────────────────────────

class GameEngine:
    """
    Orchestrator / service layer.

    Wires together Board, RuleEngine, and RealTimeArbiter.
    All three are injected — no hard-coded construction here.
    No UI, no pixels, no threads, no sleep.
    """

    def __init__(self, board: Board, rule_engine: RuleEngine, arbiter: RealTimeArbiter):
        self._board       = board
        self._rules       = rule_engine
        self._arbiter     = arbiter
        self._scores      = {WHITE: 0, BLACK: 0}
        self._game_over   = False
        self._winner: Optional[str] = None

    # ── public interface ───────────────────────────────────────────────

    def request_move(self, src: Position, dst: Position) -> RequestMoveResult:
        """
        Gate for all move requests.

        Steps (in order):
        1. Reject if game is already over.
        2. Reject if the piece at src is already in motion.
        3. Validate geometry/rules via RuleEngine.
        4. If valid, register the motion with the Arbiter.
        """
        if self._game_over:
            return RequestMoveResult.GAME_OVER

        if self._is_piece_busy(src):
            return RequestMoveResult.PIECE_BUSY

        status = self._rules.validate_move(self._board, Move(src, dst))
        if status != MoveStatus.OK:
            return _STATUS_MAP[status]

        piece    = self._board.get_piece(src)   # guaranteed non-None after OK
        duration = MOVE_DURATION_MS.get(piece.type_code, 1000)
        self._arbiter.start_motion(piece, src, dst, duration)
        return RequestMoveResult.ACCEPTED

    def tick(self, delta_ms: int) -> None:
        """
        Advance logical time by delta_ms.
        Processes every motion that completes in this tick.
        Sets game_over=True if a King is captured.
        """
        completed = self._arbiter.advance_time(delta_ms)
        for motion in completed:
            if motion.captured is not None:
                self._apply_capture(motion.captured)

    def get_snapshot(self) -> GameSnapshot:
        """Return an immutable view of the current game state."""
        grid = tuple(tuple(row) for row in self._board._grid)

        motions = tuple(
            MotionSummary(m.piece, m.src, m.dst, m.start_time, m.end_time)
            for m in self._arbiter.active_motions
        )

        return GameSnapshot(
            grid           = grid,
            scores         = dict(self._scores),
            game_over      = self._game_over,
            winner         = self._winner,
            active_motions = motions,
        )

    # ── internals ─────────────────────────────────────────────────────

    def _is_piece_busy(self, src: Position) -> bool:
        return any(m.src == src for m in self._arbiter.active_motions)

    def _apply_capture(self, captured: Piece) -> None:
        scorer = BLACK if captured.color == WHITE else WHITE
        if captured.type_code == KING:
            self._game_over = True
            self._winner    = scorer
            self._scores[scorer] = float('inf')
        else:
            from engine.config import PIECE_SCORE
            self._scores[scorer] += PIECE_SCORE.get(captured.type_code, 0)
