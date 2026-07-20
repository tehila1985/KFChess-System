from __future__ import annotations

from dataclasses import dataclass
from engine.game_engine import RequestMoveResult


@dataclass(frozen=True)
class ActionOutcome:
    success: bool
    reason: RequestMoveResult | None = None

    @staticmethod
    def ok() -> "ActionOutcome":
        return ActionOutcome(success=True, reason=RequestMoveResult.ACCEPTED)

    @staticmethod
    def fail(reason: RequestMoveResult) -> "ActionOutcome":
        return ActionOutcome(success=False, reason=reason)
