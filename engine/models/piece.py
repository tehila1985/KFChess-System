from dataclasses import dataclass


# Piece הוא אובייקט נתונים טהור — אין לו לוגיקה, רק זהות.
# frozen=True — בטוח לשימוש כ-key ב-dict/set, ולא ניתן לשינוי בטעות.
@dataclass(frozen=True)
class Piece:
    color:     str  # 'w' או 'b'
    type_code: str  # 'K', 'Q', 'R', 'B', 'N', 'P'

    @property
    def token(self) -> str:
        # הייצוג המחרוזתי שמאוחסן בגריד, למשל 'wK', 'bP'
        return self.color + self.type_code

    @staticmethod
    def from_token(token: str) -> "Piece":
        # פרסור token מהגריד חזרה לאובייקט Piece
        return Piece(color=token[0], type_code=token[1])
