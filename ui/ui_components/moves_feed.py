from __future__ import annotations

from dataclasses import dataclass, field

from ui.config.app_config import DEFAULT_APP_CONFIG, UiPieceCatalogConfig
from ui.state.game_events import MoveAccepted
from ui.state.observer import Subject, Subscription


def _make_notation_lookup(catalog: UiPieceCatalogConfig) -> dict[str, str]:
    """Build piece_type → notation_prefix from config. Falls back to type_code."""
    return dict(catalog.piece_notation)


@dataclass
class MovesFeed:
    white_entries: list[str] = field(default_factory=list)
    black_entries: list[str] = field(default_factory=list)
    dirty: bool = True
    _subscription: Subscription | None = None
    _catalog: UiPieceCatalogConfig = field(
        default_factory=lambda: DEFAULT_APP_CONFIG.pieces
    )
    # Maximum entries per side kept in memory.
    # Derived from hud_layout so the list never grows beyond what the panel shows.
    _max_entries: int = field(
        default_factory=lambda: DEFAULT_APP_CONFIG.hud_layout.max_move_entries
    )

    def bind(self, subject: Subject) -> None:
        self._subscription = subject.subscribe(MoveAccepted, self._on_move)

    @staticmethod
    def _to_square(row: int, col: int) -> str:
        """Convert (row, col) to algebraic square notation e.g. (6,4) → e2."""
        return f"{chr(ord('a') + col)}{8 - row}"

    def _on_move(self, event: MoveAccepted) -> None:
        notation = _make_notation_lookup(self._catalog)
        src = self._to_square(event.src.row, event.src.col)
        dst = self._to_square(event.dst.row, event.dst.col)
        # Fall back to raw type_code if not in config mapping.
        piece_ch = notation.get(event.piece_type, event.piece_type)
        move_text = f"{piece_ch}{src}-{dst}"

        if event.side == "w":
            self.white_entries.append(move_text)
            if len(self.white_entries) > self._max_entries:
                self.white_entries = self.white_entries[-self._max_entries:]
        elif event.side == "b":
            self.black_entries.append(move_text)
            if len(self.black_entries) > self._max_entries:
                self.black_entries = self.black_entries[-self._max_entries:]
        self.dirty = True
