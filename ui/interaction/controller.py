from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from engine.game_engine import RequestMoveResult
from engine.models.position import Position
from ui.interaction.board_mapper import BoardMapper
from ui.state.outcome import ActionOutcome


class _MoveRequester(Protocol):
    def get_piece_at(self, pos: Position):
        ...

    def is_on_cooldown(self, pos: Position) -> bool:
        ...

    def is_game_over(self) -> bool:
        ...

    def request_move(self, src: Position, dst: Position) -> RequestMoveResult:
        ...


class Controller:
    """Translates two-click UI input into move requests."""

    def __init__(self, engine: _MoveRequester, mapper: BoardMapper):
        self._engine = engine
        self._mapper = mapper
        self._src: Optional[Position] = None

    @property
    def pending_src(self) -> Optional[Position]:
        """The currently selected source square (or None)."""
        return self._src

    def on_click(self, x: int, y: int) -> Optional[RequestMoveResult]:
        pos = self._mapper.to_position(x, y)

        if pos is None:
            self._src = None
            return None

        if self._src is None:
            if self._engine.get_piece_at(pos) is None:
                return None
            if self._engine.is_on_cooldown(pos) and not self._engine.is_game_over():
                return None
            self._src = pos
            return None

        src = self._src
        src_piece = self._engine.get_piece_at(src)
        if src_piece is None:
            # Selection became stale (for example, piece was moved while selected).
            self._src = pos if self._engine.get_piece_at(pos) is not None else None
            return None

        dst_piece = self._engine.get_piece_at(pos)
        if dst_piece is not None and src_piece.color == dst_piece.color:
            self._src = pos
            return None

        self._src = None
        return self._engine.request_move(src, pos)


@dataclass
class ControllerOutcomeAdapter:
    """Adapts controller results to a stable UI outcome object."""

    controller: Controller

    @property
    def pending_src(self):
        return self.controller.pending_src

    def on_click(self, x: int, y: int) -> ActionOutcome | None:
        result = self.controller.on_click(x, y)
        if result is None:
            return None
        if isinstance(result, ActionOutcome):
            return result
        if result == RequestMoveResult.ACCEPTED:
            return ActionOutcome.ok()
        return ActionOutcome.fail(result)
