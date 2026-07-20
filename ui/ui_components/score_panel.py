from __future__ import annotations

from dataclasses import dataclass, field

from ui.state.game_events import PieceCaptured
from ui.state.observer import Subject, Subscription

# Piece value order for sorting the captured-symbols display (highest first).
_PIECE_ORDER = {"Q": 0, "R": 1, "B": 2, "N": 3, "P": 4, "K": 5}

_PIECE_SYMBOL: dict[str, str] = {
    "K": "K", "Q": "Q", "R": "R", "B": "B", "N": "N", "P": "P",
}


@dataclass
class ScorePanel:
    white_captures: int = 0
    black_captures: int = 0
    # Pre-computed symbol strings — updated only on capture events,
    # never recomputed during rendering.
    white_symbols: str = ""
    black_symbols: str = ""
    # Internal piece lists used only to rebuild the symbol string.
    _white_pieces: list[str] = field(default_factory=list)
    _black_pieces: list[str] = field(default_factory=list)
    dirty: bool = True
    _subscription: Subscription | None = None

    def bind(self, subject: Subject) -> None:
        self._subscription = subject.subscribe(PieceCaptured, self._on_capture)

    def _on_capture(self, event: PieceCaptured) -> None:
        piece_sym = _PIECE_SYMBOL.get(event.captured_type, event.captured_type)
        if event.captured_side == "w":
            self.black_captures += event.points
            self._black_pieces.append(piece_sym)
            self.black_symbols = self._build_symbols(self._black_pieces)
        else:
            self.white_captures += event.points
            self._white_pieces.append(piece_sym)
            self.white_symbols = self._build_symbols(self._white_pieces)
        self.dirty = True

    @staticmethod
    def _build_symbols(pieces: list[str]) -> str:
        """Sort by piece value (highest first) and join with spaces."""
        return " ".join(sorted(pieces, key=lambda p: _PIECE_ORDER.get(p, 9)))
