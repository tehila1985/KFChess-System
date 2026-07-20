from ui.runtime.game_loop import LEFT_ACTION, RIGHT_ACTION, _process_pointer_action


# ── runtime pointer routing ───────────────────────────────────────────


class _MapperStub:
    def __init__(self, pos):
        self._pos = pos
        self.calls: list[tuple[int, int]] = []

    def to_position(self, x: int, y: int):
        self.calls.append((x, y))
        return self._pos


class _FacadeStub:
    def __init__(self) -> None:
        self.jump_calls = []

    def request_jump(self, pos) -> None:
        self.jump_calls.append(pos)


class _ResultStub:
    def __init__(self, success: bool, reason_name: str | None = None) -> None:
        self.success = success
        self.reason = None if reason_name is None else type("Reason", (), {"name": reason_name})()


class _ControllerStub:
    def __init__(self, result):
        self._result = result
        self.calls: list[tuple[int, int]] = []

    def on_click(self, x: int, y: int):
        self.calls.append((x, y))
        return self._result


def test_right_click_requests_jump_on_mapped_square() -> None:
    """Verify right click requests jump on mapped square."""
    mapper = _MapperStub(pos="p")
    facade = _FacadeStub()
    controller = _ControllerStub(result=None)

    status = _process_pointer_action(
        action=RIGHT_ACTION,
        x=300,
        y=120,
        sidebar_width=210,
        mapper=mapper,
        facade=facade,
        ui_controller=controller,
        current_status="idle",
    )

    assert mapper.calls == [(90, 120)]
    assert facade.jump_calls == ["p"]
    assert status == "Jump requested"


def test_right_click_outside_board_keeps_status_and_skips_jump() -> None:
    """Verify right click outside board keeps status and skips jump."""
    mapper = _MapperStub(pos=None)
    facade = _FacadeStub()
    controller = _ControllerStub(result=None)

    status = _process_pointer_action(
        action=RIGHT_ACTION,
        x=100,
        y=120,
        sidebar_width=210,
        mapper=mapper,
        facade=facade,
        ui_controller=controller,
        current_status="idle",
    )

    assert mapper.calls == [(-110, 120)]
    assert facade.jump_calls == []
    assert status == "idle"


def test_left_click_still_routes_to_move_controller() -> None:
    """Verify left click still routes to move controller."""
    mapper = _MapperStub(pos=None)
    facade = _FacadeStub()
    controller = _ControllerStub(result=_ResultStub(success=True))

    status = _process_pointer_action(
        action=LEFT_ACTION,
        x=310,
        y=140,
        sidebar_width=210,
        mapper=mapper,
        facade=facade,
        ui_controller=controller,
        current_status="idle",
    )

    assert controller.calls == [(100, 140)]
    assert facade.jump_calls == []
    assert status == "Move accepted"
