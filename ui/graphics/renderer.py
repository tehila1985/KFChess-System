from __future__ import annotations

from engine.game_engine import GameSnapshot
from ui.vendor.img import Img


class Renderer:
    """Composes board and pieces onto a frame using Img only."""

    def __init__(self, board_img: Img) -> None:
        self._board_img = board_img

    def render(self, snapshot: GameSnapshot) -> Img:
        # Skeleton implementation: return board frame for now.
        _ = snapshot
        return self._board_img
