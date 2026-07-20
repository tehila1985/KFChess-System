from __future__ import annotations

from dataclasses import dataclass, field

from ui.state.game_events import PieceCaptured
from ui.state.observer import Subject, Subscription

# Piece value order for sorting the captured-symbols display (highest first).
_PIECE_ORDER = {"Q": 0, "R": 1, "B": 2, "N": 3, "P": 4, "K": 5}

# Single character to show per captured piece type.
_PIECE_SYMBOL: dict[str, str] = {
    "K": "K", "Q": "Q", "R": "R", "B": "B", "N": "N", "P": "P",
}


@dataclass
class ScorePanel:
    white_captures: int = 0
    black_captures: int = 0
    # Piece types captured BY each side (list, may contain duplicates).
    white_captured_pieces: list[str] = field(default_factory=list)
    black_captured_pieces: list[str] = field(default_factory=list)
    dirty: bool = True
    _subscription: Subscription | None = None

    def bind(self, subject: Subject) -> None:
        self._subscription = subject.subscribe(PieceCaptured, self._on_capture)

    def _on_capture(self, event: PieceCaptured) -> None:
        piece_sym = _PIECE_SYMBOL.get(event.captured_type, event.captured_type)
        if event.captured_side == "w":
            # White piece captured → black scores
            self.black_captures += event.points
            self.black_captured_pieces.append(piece_sym)
        else:
            # Black piece captured → white scores
            self.white_captures += event.points
            self.white_captured_pieces.append(piece_sym)
        self.dirty = True

    @property
    def white_symbols(self) -> str:
        """Captured piece symbols for display next to white's score."""
        return self._format_symbols(self.white_captured_pieces)

    @property
    def black_symbols(self) -> str:
        """Captured piece symbols for display next to black's score."""
        return self._format_symbols(self.black_captured_pieces)

    @staticmethod
    def _format_symbols(pieces: list[str]) -> str:
        """Sort by piece value (highest first) and join with spaces."""
        sorted_pieces = sorted(pieces, key=lambda p: _PIECE_ORDER.get(p, 9))
        return " ".join(sorted_pieces)
