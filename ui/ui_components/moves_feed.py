from __future__ import annotations

from dataclasses import dataclass, field

from ui.state.game_events import MoveAccepted
from ui.state.observer import Subject, Subscription

# Piece-type display characters (upper-case standard algebraic notation).
_PIECE_DISPLAY: dict[str, str] = {
    "K": "K", "Q": "Q", "R": "R", "B": "B", "N": "N", "P": "",
}


@dataclass
class MovesFeed:
    white_entries: list[str] = field(default_factory=list)
    black_entries: list[str] = field(default_factory=list)
    dirty: bool = True
    _subscription: Subscription | None = None

    def bind(self, subject: Subject) -> None:
        self._subscription = subject.subscribe(MoveAccepted, self._on_move)

    @staticmethod
    def _to_square(row: int, col: int) -> str:
        """Convert (row, col) to algebraic square notation e.g. (6,4) -> e2."""
        return f"{chr(ord('a') + col)}{8 - row}"

    # Maximum entries kept per side — prevents unbounded list growth that
    # slows down rendering after many moves.
    _MAX_ENTRIES: int = 60

    def _on_move(self, event: MoveAccepted) -> None:
        src = self._to_square(event.src.row, event.src.col)
        dst = self._to_square(event.dst.row, event.dst.col)
        piece_ch = _PIECE_DISPLAY.get(event.piece_type, event.piece_type)
        move_text = f"{piece_ch}{src}-{dst}"
        if event.side == "w":
            self.white_entries.append(move_text)
            if len(self.white_entries) > self._MAX_ENTRIES:
                self.white_entries = self.white_entries[-self._MAX_ENTRIES:]
        elif event.side == "b":
            self.black_entries.append(move_text)
            if len(self.black_entries) > self._MAX_ENTRIES:
                self.black_entries = self.black_entries[-self._MAX_ENTRIES:]
        self.dirty = True
