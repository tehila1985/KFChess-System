from __future__ import annotations

from dataclasses import dataclass, field

from ui.state.game_events import MoveAccepted
from ui.state.observer import Subject, Subscription


@dataclass
class MovesFeed:
    entries: list[str] = field(default_factory=list)
    _subscription: Subscription | None = None

    def bind(self, subject: Subject) -> None:
        self._subscription = subject.subscribe(MoveAccepted, self._on_move)

    def _on_move(self, event: MoveAccepted) -> None:
        self.entries.append(f"{event.src} -> {event.dst}")
