from __future__ import annotations

from dataclasses import dataclass

from ui.state.game_events import PieceCaptured
from ui.state.observer import Subject, Subscription


@dataclass
class ScorePanel:
    white_captures: int = 0
    black_captures: int = 0
    _subscription: Subscription | None = None

    def bind(self, subject: Subject) -> None:
        self._subscription = subject.subscribe(PieceCaptured, self._on_capture)

    def _on_capture(self, event: PieceCaptured) -> None:
        if event.captured_side == "w":
            self.black_captures += 1
        else:
            self.white_captures += 1
