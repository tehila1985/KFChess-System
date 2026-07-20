from server.game_engine import RequestMoveResult
from ui.interaction.controller_outcome import ControllerOutcomeAdapter
from ui.state.outcome import ActionOutcome


class _ControllerStub:
    def __init__(self, result):
        self._result = result
        self.pending_src = None

    def on_click(self, x: int, y: int):
        _ = (x, y)
        return self._result


def test_adapter_returns_none_when_controller_returns_none() -> None:
    """Verify adapter returns none when controller returns none."""
    adapter = ControllerOutcomeAdapter(_ControllerStub(None))
    assert adapter.on_click(1, 2) is None


def test_adapter_maps_accept_to_success_outcome() -> None:
    """Verify adapter maps accept to success outcome."""
    adapter = ControllerOutcomeAdapter(_ControllerStub(RequestMoveResult.ACCEPTED))
    assert adapter.on_click(1, 2) == ActionOutcome.ok()


def test_adapter_maps_failure_to_failed_outcome() -> None:
    """Verify adapter maps failure to failed outcome."""
    adapter = ControllerOutcomeAdapter(_ControllerStub(RequestMoveResult.ILLEGAL_PIECE_MOVE))
    assert adapter.on_click(1, 2) == ActionOutcome.fail(RequestMoveResult.ILLEGAL_PIECE_MOVE)


def test_adapter_passes_through_action_outcome() -> None:
    """Verify adapter passes through action outcome."""
    expected = ActionOutcome.fail(RequestMoveResult.PIECE_ON_COOLDOWN)
    adapter = ControllerOutcomeAdapter(_ControllerStub(expected))
    assert adapter.on_click(1, 2) == expected
