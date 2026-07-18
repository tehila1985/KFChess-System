from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ui.vendor.img import Img


@dataclass(frozen=True)
class RenderContext:
    elapsed_ms: int
    status_line: str
    selected_pos: tuple[int, int] | None
    legal_targets: tuple[tuple[int, int], ...]


class IRenderer(Protocol):
    def draw(self, scene: Img, ctx: RenderContext) -> Img:
        ...
