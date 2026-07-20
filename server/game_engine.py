from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from server.models.board import Board
from server.models.move import Move
from server.models.piece import Piece
from server.models.position import Position
from server.rules.rule_engine import MoveStatus, RuleEngine
from server.arbiter.real_time_arbiter import RealTimeArbiter
from server.config import WHITE, BLACK, KING, QUEEN, PAWN, GameConfig, DEFAULT_CONFIG


class RequestMoveResult(Enum):
    """Result of a move request — returned to Controller after request_move."""
    ACCEPTED             = auto()  # motion accepted and on its way
    GAME_OVER            = auto()  # game has ended, no moves accepted
    PIECE_BUSY           = auto()  # piece is already in motion
    PIECE_ON_COOLDOWN    = auto()  # piece is cooling down and cannot move yet
    OUTSIDE_BOARD        = auto()
    EMPTY_SOURCE         = auto()
    FRIENDLY_DESTINATION = auto()
    ILLEGAL_PIECE_MOVE   = auto()


# mapping from MoveStatus (rules layer) to RequestMoveResult (engine layer)
_STATUS_MAP: dict[MoveStatus, RequestMoveResult] = {
    MoveStatus.OK:                   RequestMoveResult.ACCEPTED,
    MoveStatus.OUTSIDE_BOARD:        RequestMoveResult.OUTSIDE_BOARD,
    MoveStatus.EMPTY_SOURCE:         RequestMoveResult.EMPTY_SOURCE,
    MoveStatus.FRIENDLY_DESTINATION: RequestMoveResult.FRIENDLY_DESTINATION,
    MoveStatus.ILLEGAL_PIECE_MOVE:   RequestMoveResult.ILLEGAL_PIECE_MOVE,
}


@dataclass(frozen=True)
class MotionSummary:
    """Summary of an active motion — part of GameSnapshot for UI use."""
    piece:      Piece
    src:        Position
    dst:        Position
    start_time: int
    end_time:   int
    is_jump:    bool = False


@dataclass(frozen=True)
class GameSnapshot:
    """
    Snapshot of the game state at a given point in time.

    Created by get_snapshot() and passed to TextRenderer.
    frozen — immutable, safe to pass to the UI layer.
    """
    grid:           tuple   # current grid (including pieces in motion at their src)
    scores:         tuple
    game_over:      bool
    winner:         Optional[str]
    active_motions: tuple   # MotionSummary of all active motions
    cooldowns:      tuple = field(default_factory=tuple)   # tuple[(Position, end_time_ms)] for cooldown visualization


class GameEngine:
    """
    Game engine — coordinates all layers.

    Responsibilities:
    - Receiving move requests from Controller and validating them via RuleEngine
    - Forwarding approved moves to RealTimeArbiter
    - Advancing time (tick) and handling results (capture, pawn promotion)
    - Managing scores and game_over state
    - Producing GameSnapshot for display

    Has no knowledge of UI or pixels.
    """

    def __init__(self, board: Board, rule_engine: RuleEngine, arbiter: RealTimeArbiter,
                 config: GameConfig = DEFAULT_CONFIG):
        self._board     = board
        self._rules     = rule_engine
        self._arbiter   = arbiter
        self._config    = config  # injected game values — not imported directly
        self._scores    = {WHITE: 0, BLACK: 0}
        self._game_over = False
        self._winner: Optional[str] = None

    def get_piece_at(self, pos: Position) -> Optional[Piece]:
        """
        Returns the piece at the square — whether on the board or in motion.

        A piece in motion is removed from the grid at start_motion, so active_motions is also checked.
        """
        piece = self._board.get_piece(pos)
        if piece is not None:
            return piece
        for m in self._arbiter.active_motions:
            if m.src == pos:
                return m.piece
        return None

    @property
    def current_time(self) -> int:
        return self._arbiter.current_time

    def request_move(self, src: Position, dst: Position) -> RequestMoveResult:
        """
        Attempts to start a motion from src to dst.

        Validation order:
        1. game_over — no moves accepted
        2. piece is busy (already in motion)
        3. legality check via RuleEngine
        4. compute duration based on piece type and distance
        5. hand off to Arbiter
        """
        if self._game_over:
            return RequestMoveResult.GAME_OVER

        if self._is_piece_busy(src):
            return RequestMoveResult.PIECE_BUSY

        if self._arbiter.is_on_cooldown(src):
            return RequestMoveResult.PIECE_ON_COOLDOWN

        status = self._rules.validate_move(self._board, Move(src, dst))
        if status != MoveStatus.OK:
            return _STATUS_MAP[status]

        piece    = self._board.get_piece(src)
        speed    = self._config.move_duration_ms.get(piece.type_code, 1000)
        distance = max(abs(dst.row - src.row), abs(dst.col - src.col))
        duration = speed * distance
        self._arbiter.start_motion(piece, src, dst, duration)
        return RequestMoveResult.ACCEPTED

    def get_legal_destinations(self, src: Position) -> tuple[Position, ...]:
        if self._game_over:
            return ()
        if not self._board.in_bounds(src):
            return ()
        if self._is_piece_busy(src):
            return ()
        if self._arbiter.is_on_cooldown(src):
            return ()
        if self._board.get_piece(src) is None:
            return ()

        legal: list[Position] = []
        for row in range(self._board.rows):
            for col in range(self._board.cols):
                dst = Position(row, col)
                if dst == src:
                    continue
                status = self._rules.validate_move(self._board, Move(src, dst))
                if status == MoveStatus.OK:
                    legal.append(dst)
        return tuple(legal)

    def is_on_cooldown(self, pos: Position) -> bool:
        return self._arbiter.is_on_cooldown(pos)

    def is_game_over(self) -> bool:
        return self._game_over

    def request_jump(self, pos: Position) -> None:
        """
        Performs a jump for the piece at square pos.

        A jump is only possible if the piece is not currently in motion.
        The piece stays on its square but is marked as airborne — it can capture arriving enemies.
        """
        if self._game_over:
            return
        if not self._board.in_bounds(pos):
            return
        if self._board.get_piece(pos) is None:
            return
        if self._is_piece_busy(pos):
            return
        self._arbiter.start_jump(pos)

    def tick(self, delta_ms: int) -> None:
        """
        Advances time by delta_ms and handles completed motions.

        For each completed motion:
        - if a pawn reached the far end — promote it to queen
        - if there was a capture — call _apply_capture
        """
        completed = self._arbiter.advance_time(delta_ms)
        for motion in completed:
            dst   = motion.dst
            piece = self._board.get_piece(dst)
            # pawn promotion: reached row 0 (white) or last row (black)
            if piece is not None and piece.type_code == PAWN:
                promotion_row = 0 if piece.color == WHITE else self._board.rows - 1
                if dst.row == promotion_row:
                    self._board.set_piece(dst, Piece(piece.color, QUEEN))
            if motion.captured is not None:
                self._apply_capture(motion.captured)

    def get_snapshot(self) -> GameSnapshot:
        """
        Returns the current game state snapshot.

        Pieces in motion are shown at their src in the grid (so the UI can see them).
        Jumps (is_jump) are not shown at src because the piece is already visible on the board.
        """
        grid = [list(row) for row in self._board._grid]
        for m in self._arbiter.active_motions:
            if not m.is_jump and grid[m.src.row][m.src.col] == ".":
                grid[m.src.row][m.src.col] = m.piece.token
        frozen_grid = tuple(tuple(row) for row in grid)
        motions = tuple(
            MotionSummary(m.piece, m.src, m.dst, m.start_time, m.end_time, m.is_jump)
            for m in self._arbiter.active_motions
        )
        return GameSnapshot(
            grid           = frozen_grid,
            scores         = tuple(sorted(self._scores.items())),
            game_over      = self._game_over,
            winner         = self._winner,
            active_motions = motions,
            cooldowns      = tuple(self._arbiter.cooldowns.items()),
        )

    def _is_piece_busy(self, src: Position) -> bool:
        """A piece is busy if there is an active motion (including a jump) originating from src."""
        return any(m.src == src for m in self._arbiter.active_motions)

    def _apply_capture(self, captured: Piece) -> None:
        """
        Handles a piece capture:
        - capturing the king -> game_over, capturing side's score = infinity
        - capturing any other piece -> adds score to the capturing side
        """
        scorer = BLACK if captured.color == WHITE else WHITE
        if captured.type_code == KING:
            self._game_over = True
            self._winner    = scorer
            self._scores[scorer] = float('inf')
        else:
            self._scores[scorer] += self._config.piece_score.get(captured.type_code, 0)
