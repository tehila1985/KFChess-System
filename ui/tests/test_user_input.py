from ui.user_input.mouse_controller import MouseController


class _ControllerStub:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def on_click(self, x: int, y: int):
        self.calls.append((x, y))
        return "ok"


def test_mouse_controller_delegates_to_controller() -> None:
    controller = _ControllerStub()
    mouse = MouseController(controller)

    result = mouse.on_pointer(12, 34)

    assert result == "ok"
    assert controller.calls == [(12, 34)]
