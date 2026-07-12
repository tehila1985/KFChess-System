from dataclasses import dataclass
from engine.models.position import Position


# Move represents a move request: from square src to square dst.
# Pure data object — created in Controller and passed to RuleEngine for validation.
@dataclass(frozen=True)
class Move:
    src: Position
    dst: Position
