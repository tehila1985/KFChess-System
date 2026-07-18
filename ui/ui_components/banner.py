from __future__ import annotations

from dataclasses import dataclass

from ui.state.game_events import GameOver
from ui.state.observer import Subject, Subscription


@dataclass
class Banner:
    message: str = ""
    _subscription: Subscription | None = None

    def bind(self, subject: Subject) -> None:
        self._subscription = subject.subscribe(GameOver, self._on_game_over)

    def _on_game_over(self, event: GameOver) -> None:
        winner = event.winner or "unknown"
        self.message = f"Game Over - winner: {winner}"
