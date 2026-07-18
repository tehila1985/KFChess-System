from __future__ import annotations

from dataclasses import dataclass

from engine.game_engine import RequestMoveResult
from ui.controller import Controller
from ui.state.outcome import ActionOutcome


@dataclass
class ControllerOutcomeAdapter:
    controller: Controller

    @property
    def pending_src(self):
        return self.controller.pending_src

    def on_click(self, x: int, y: int) -> ActionOutcome | None:
        result = self.controller.on_click(x, y)
        if result is None:
            return None
        if result == RequestMoveResult.ACCEPTED:
            return ActionOutcome.ok()
        return ActionOutcome.fail(result)
