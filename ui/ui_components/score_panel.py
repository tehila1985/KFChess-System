from __future__ import annotations

from dataclasses import dataclass, field

from ui.config.app_config import DEFAULT_APP_CONFIG, UiPieceCatalogConfig
from ui.state.game_events import PieceCaptured
from ui.state.observer import Subject, Subscription


def _make_symbol_lookup(catalog: UiPieceCatalogConfig) -> dict[str, str]:
    """Build piece_type → display_symbol from config. Falls back to type_code."""
    return dict(catalog.piece_symbol)


def _make_order_lookup(catalog: UiPieceCatalogConfig) -> dict[str, int]:
    """Build piece_type → sort_index from config. Unlisted types sort last."""
    return {t: i for i, t in enumerate(catalog.piece_capture_order)}


@dataclass
class ScorePanel:
    white_captures: int = 0
    black_captures: int = 0
    # Pre-computed symbol strings — rebuilt only on capture events.
    white_symbols: str = ""
    black_symbols: str = ""
    # Internal piece lists used only to rebuild the symbol string.
    _white_pieces: list[str] = field(default_factory=list)
    _black_pieces: list[str] = field(default_factory=list)
    dirty: bool = True
    _subscription: Subscription | None = None
    _catalog: UiPieceCatalogConfig = field(
        default_factory=lambda: DEFAULT_APP_CONFIG.pieces
    )

    def bind(self, subject: Subject) -> None:
        self._subscription = subject.subscribe(PieceCaptured, self._on_capture)

    def _on_capture(self, event: PieceCaptured) -> None:
        symbol_map = _make_symbol_lookup(self._catalog)
        order_map = _make_order_lookup(self._catalog)
        # Fall back to the raw type_code if it's not in the config mapping.
        piece_sym = symbol_map.get(event.captured_type, event.captured_type)

        if event.captured_side == "w":
            self.black_captures += event.points
            self._black_pieces.append(piece_sym)
            self.black_symbols = _build_symbols(self._black_pieces, order_map)
        else:
            self.white_captures += event.points
            self._white_pieces.append(piece_sym)
            self.white_symbols = _build_symbols(self._white_pieces, order_map)
        self.dirty = True


def _build_symbols(pieces: list[str], order: dict[str, int]) -> str:
    """Sort pieces by configured capture order (highest value first) and join."""
    last = len(order)
    return " ".join(sorted(pieces, key=lambda p: order.get(p, last)))
