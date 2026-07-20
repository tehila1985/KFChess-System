from dataclasses import dataclass


# Position represents a cell address on the board.
# frozen=True — immutable after creation, safe to use as a dict/set key.
@dataclass(frozen=True)
class Position:
    row: int  # row (0 = top row)
    col: int  # column (0 = leftmost column)
