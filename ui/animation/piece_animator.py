from __future__ import annotations

from dataclasses import dataclass

from ui.config.app_config import DEFAULT_APP_CONFIG


@dataclass
class PieceAnimator:
    """Minimal stateful animator placeholder keyed by piece token."""

    token: str
    state: str = DEFAULT_APP_CONFIG.pieces.default_state
    elapsed_ms: int = 0

    def set_state(self, state: str) -> None:
        self.state = state
        self.elapsed_ms = 0

    def tick(self, delta_ms: int) -> None:
        self.elapsed_ms += max(0, delta_ms)
