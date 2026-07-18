from __future__ import annotations

from dataclasses import dataclass, field

from ui.state.game_events import MoveAccepted
from ui.state.observer import Subject, Subscription


@dataclass
class MovesFeed:
    entries: list[str] = field(default_factory=list)
    white_entries: list[str] = field(default_factory=list)
    black_entries: list[str] = field(default_factory=list)
    dirty: bool = True
    _subscription: Subscription | None = None

    def bind(self, subject: Subject) -> None:
        self._subscription = subject.subscribe(MoveAccepted, self._on_move)

    @staticmethod
    def _to_square(pos_row: int, pos_col: int) -> str:
        file_char = chr(ord("a") + pos_col)
        rank = 8 - pos_row
        return f"{file_char}{rank}"

    def _on_move(self, event: MoveAccepted) -> None:
        src = self._to_square(event.src.row, event.src.col)
        dst = self._to_square(event.dst.row, event.dst.col)
        seconds = event.at_ms / 1000.0
        move_text = f"{event.piece_type}{src}-{dst} [{seconds:.1f}s]"
        self.entries.append(move_text)
        if event.side == "w":
            self.white_entries.append(move_text)
        elif event.side == "b":
            self.black_entries.append(move_text)
        self.dirty = True
