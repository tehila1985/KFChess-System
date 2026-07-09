from dataclasses import dataclass


@dataclass(frozen=True)
class Piece:
    """
    Pure data representation of a chess piece.
    color: 'w' or 'b'
    type_code: 'K', 'Q', 'R', 'B', 'N', or 'P'
    token: e.g. 'wK', 'bP' — matches the existing board string format.
    """
    color: str
    type_code: str

    @property
    def token(self) -> str:
        return self.color + self.type_code

    @staticmethod
    def from_token(token: str) -> "Piece":
        return Piece(color=token[0], type_code=token[1])
