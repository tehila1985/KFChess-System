from typing import Optional
from engine.game_engine import GameEngine, RequestMoveResult
from engine.models.position import Position
from ui.board_mapper import BoardMapper


class Controller:
    def __init__(self, engine: GameEngine, mapper: BoardMapper):
        self._engine = engine
        self._mapper = mapper
        self._src: Optional[Position] = None

    @property
    def pending_src(self) -> Optional[Position]:
        return self._src

    def on_click(self, x: int, y: int) -> Optional[RequestMoveResult]:
        pos = self._mapper.to_position(x, y)

        if pos is None:
            self._src = None
            return None

        if self._src is None:
            self._src = pos
            return None

        # אם קליקו על כלי ידידותי - החלף בחירה
        src = self._src
        src_piece = self._engine.get_piece_at(src)
        dst_piece = self._engine.get_piece_at(pos)
        if src_piece is not None and dst_piece is not None and src_piece.color == dst_piece.color:
            self._src = pos
            return None

        self._src = None
        return self._engine.request_move(src, pos)
