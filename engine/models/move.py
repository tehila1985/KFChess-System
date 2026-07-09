from dataclasses import dataclass
from engine.models.position import Position


@dataclass(frozen=True)
class Move:
    src: Position
    dst: Position
