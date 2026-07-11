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
from engine.config import WHITE, BLACK, KING, QUEEN, PAWN,PIECE_SCORE, MOVE_DURATION_MS, PIXEL_TO_GRID_DIVISOR


class RequestMoveResult(Enum):
    ACCEPTED             = auto()
    GAME_OVER            = auto()
    PIECE_BUSY           = auto()
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


@dataclass(frozen=True)
class MotionSummary:
    piece:      Piece
    src:        Position
    dst:        Position
    start_time: int
    end_time:   int


@dataclass(frozen=True)
class GameSnapshot:
    grid:           tuple
    scores:         dict
    game_over:      bool
    winner:         Optional[str]
    active_motions: tuple


class GameEngine:
    def __init__(self, board: Board, rule_engine: RuleEngine, arbiter: RealTimeArbiter):
        self._board     = board
        self._rules     = rule_engine
        self._arbiter   = arbiter
        self._scores    = {WHITE: 0, BLACK: 0}
        self._game_over = False
        self._winner: Optional[str] = None

    def get_piece_at(self, pos: Position) -> Optional[Piece]:
        # בדוק גם בלוח וגם בתנועות פעילות
        piece = self._board.get_piece(pos)
        if piece is not None:
            return piece
        # כלי שנמצא בתנועה - src שלו נמחק מהלוח, חפש לפי dst
        for m in self._arbiter.active_motions:
            if m.src == pos:
                return m.piece
        return None

    def request_move(self, src: Position, dst: Position) -> RequestMoveResult:
        if self._game_over:
            return RequestMoveResult.GAME_OVER

        if self._is_piece_busy(src):
            return RequestMoveResult.PIECE_BUSY

        status = self._rules.validate_move(self._board, Move(src, dst))
        if status != MoveStatus.OK:
            return _STATUS_MAP[status]

        piece    = self._board.get_piece(src)
        speed    = MOVE_DURATION_MS.get(piece.type_code, 1000)
        distance = max(abs(dst.row - src.row), abs(dst.col - src.col))
        duration = speed * distance
        self._arbiter.start_motion(piece, src, dst, duration)
        return RequestMoveResult.ACCEPTED

    def request_jump(self, x: int, y: int) -> None:
        if self._game_over:
            return
        col = x // PIXEL_TO_GRID_DIVISOR
        row = y // PIXEL_TO_GRID_DIVISOR
        pos = Position(row, col)
        if not self._board.in_bounds(pos):
            return
        if self._board.get_piece(pos) is None:
            return
        if self._is_piece_busy(pos):
            return
        self._arbiter.start_jump(pos)

    def tick(self, delta_ms: int) -> None:
        completed = self._arbiter.advance_time(delta_ms)
        for motion in completed:
            # promotion: חייל שהגיע לקצה הלוח
            dst = motion.dst
            piece = self._board.get_piece(dst)
            if piece is not None and piece.type_code == PAWN:
                promotion_row = 0 if piece.color == WHITE else self._board.rows - 1
                if dst.row == promotion_row:
                    self._board.set_piece(dst, Piece(piece.color, QUEEN))
            if motion.captured is not None:
                self._apply_capture(motion.captured)

    def get_snapshot(self) -> GameSnapshot:
        # בנה grid עם כלים בתנועה מוצגים ב-src שלהם
        grid = [list(row) for row in self._board._grid]
        for m in self._arbiter.active_motions:
            if not m.is_jump and grid[m.src.row][m.src.col] == ".":
                grid[m.src.row][m.src.col] = m.piece.token
        frozen_grid = tuple(tuple(row) for row in grid)
        motions = tuple(
            MotionSummary(m.piece, m.src, m.dst, m.start_time, m.end_time)
            for m in self._arbiter.active_motions
        )
        return GameSnapshot(
            grid           = frozen_grid,
            scores         = dict(self._scores),
            game_over      = self._game_over,
            winner         = self._winner,
            active_motions = motions,
        )

    def _is_piece_busy(self, src: Position) -> bool:
        # כלי עסוק אם יש תנועה פעילה שיצאה מ-src, או קפיצה שנמצאת ב-src
        return any(m.src == src for m in self._arbiter.active_motions)

    def _apply_capture(self, captured: Piece) -> None:
        scorer = BLACK if captured.color == WHITE else WHITE
        if captured.type_code == KING:
            self._game_over = True
            self._winner    = scorer
            self._scores[scorer] = float('inf')
        else:
            self._scores[scorer] += PIECE_SCORE.get(captured.type_code, 0)
