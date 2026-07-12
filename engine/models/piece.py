from dataclasses import dataclass


# Piece is a pure data object — no logic, only identity.
# frozen=True — safe to use as a dict/set key, and cannot be accidentally mutated.
@dataclass(frozen=True)
class Piece:
    color:     str  # 'w' or 'b'
    type_code: str  # 'K', 'Q', 'R', 'B', 'N', 'P'

    @property
    def token(self) -> str:
        # the string representation stored in the grid, e.g. 'wK', 'bP'
        return self.color + self.type_code

    @staticmethod
    def from_token(token: str) -> "Piece":
        # parse a token from the grid back into a Piece object
        return Piece(color=token[0], type_code=token[1])
