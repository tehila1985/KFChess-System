"""
MouseController was removed as it was an unused wrapper that added no value.
The ControllerOutcomeAdapter in ui/interaction/controller.py is the canonical
adapter used by the runtime loop.  These tests now verify that adapter instead.
"""
from engine.game_engine import RequestMoveResult
from ui.interaction.controller import ControllerOutcomeAdapter
from ui.state.outcome import ActionOutcome


class _ControllerStub:
    def __init__(self, result) -> None:
        self._result = result
        self.calls: list[tuple[int, int]] = []
        self.pending_src = None

    def on_click(self, x: int, y: int):
        self.calls.append((x, y))
        return self._result


def test_adapter_delegates_click_coordinates() -> None:
    """Verify the adapter forwards (x, y) coordinates to the underlying controller."""
    stub = _ControllerStub(result=None)
    adapter = ControllerOutcomeAdapter(stub)

    adapter.on_click(12, 34)

    assert stub.calls == [(12, 34)]


def test_adapter_returns_none_when_controller_returns_none() -> None:
    """Verify adapter returns None when controller returns None."""
    adapter = ControllerOutcomeAdapter(_ControllerStub(None))
    assert adapter.on_click(1, 2) is None


def test_adapter_maps_accepted_to_success_outcome() -> None:
    """Verify adapter maps ACCEPTED to ActionOutcome.ok()."""
    adapter = ControllerOutcomeAdapter(_ControllerStub(RequestMoveResult.ACCEPTED))
    assert adapter.on_click(1, 2) == ActionOutcome.ok()


def test_adapter_maps_failure_to_failed_outcome() -> None:
    """Verify adapter maps a failure result to a failed ActionOutcome."""
    adapter = ControllerOutcomeAdapter(_ControllerStub(RequestMoveResult.ILLEGAL_PIECE_MOVE))
    assert adapter.on_click(1, 2) == ActionOutcome.fail(RequestMoveResult.ILLEGAL_PIECE_MOVE)


def test_adapter_passes_through_action_outcome_directly() -> None:
    """Verify adapter passes through an ActionOutcome returned by the controller unchanged."""
    expected = ActionOutcome.fail(RequestMoveResult.PIECE_ON_COOLDOWN)
    adapter = ControllerOutcomeAdapter(_ControllerStub(expected))
    assert adapter.on_click(1, 2) == expected
