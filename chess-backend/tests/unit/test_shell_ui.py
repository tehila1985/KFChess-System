"""
Unit tests for client/shell_ui.py — the terminal client's top-level menu loop.

PlayScreen/RoomScreen/GameScreen are already covered in their own test
files; here they're replaced with small fakes so these tests focus on
ShellUI's own dispatch/gating logic (menu choice -> action, require_login
gating, quit).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import client.shell_ui as shell_ui_module
from client.shell_ui import ShellUI
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope


class FakeSession:
    def __init__(self, authenticated=False):
        self.username = "alice" if authenticated else None
        self.elo = 1200
        self._authenticated = authenticated
        self.session_token = "tok"
        self._handlers = {}

    def is_authenticated(self):
        return self._authenticated

    def on(self, msg_type, handler):
        self._handlers[msg_type] = handler

    async def send(self, env):
        pass

    async def request(self, env, timeout=10.0):
        return Envelope(type=MessageType.LOGIN_ERROR, payload={"reason": "unused"})


class FakeClientLogger:
    def __init__(self):
        self.actions = []

    def user_action(self, action, **kwargs):
        self.actions.append((action, kwargs))


class FakePlayScreen:
    instances = []

    def __init__(self, session):
        self.session = session
        self.instances.append(self)

    async def run(self):
        return getattr(self, "_result", None)


class FakeRoomScreen:
    instances = []

    def __init__(self, session):
        self.session = session
        self.instances.append(self)

    async def run_create(self):
        return getattr(self, "_create_result", None)

    async def run_join(self):
        return getattr(self, "_join_result", None)


class FakeGameScreen:
    instances = []

    def __init__(self, session, **kwargs):
        self.session = session
        self.kwargs = kwargs
        self.instances.append(self)
        self.ran = False

    async def run(self):
        self.ran = True


@pytest.fixture(autouse=True)
def _clear_fake_instances():
    FakePlayScreen.instances.clear()
    FakeRoomScreen.instances.clear()
    FakeGameScreen.instances.clear()
    yield


def _choices(monkeypatch, *choices):
    it = iter(choices)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))


@pytest.mark.asyncio
async def test_quit_exits_loop(monkeypatch, capsys):
    _choices(monkeypatch, "5")
    ui = ShellUI(FakeSession(), FakeClientLogger())

    await ui.run()

    assert "Goodbye." in capsys.readouterr().out


@pytest.mark.asyncio
async def test_invalid_choice_reprompts_then_quits(monkeypatch, capsys):
    _choices(monkeypatch, "9", "5")
    ui = ShellUI(FakeSession(), FakeClientLogger())

    await ui.run()

    assert "Invalid choice." in capsys.readouterr().out


@pytest.mark.asyncio
async def test_play_blocked_when_not_logged_in(monkeypatch, capsys):
    _choices(monkeypatch, "3", "5")
    ui = ShellUI(FakeSession(authenticated=False), FakeClientLogger())

    await ui.run()

    assert "must be logged in" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_play_flow_with_no_match_does_not_start_game(monkeypatch):
    monkeypatch.setattr(shell_ui_module, "PlayScreen", FakePlayScreen)
    monkeypatch.setattr(shell_ui_module, "GameScreen", FakeGameScreen)
    _choices(monkeypatch, "3", "5")
    ui = ShellUI(FakeSession(authenticated=True), FakeClientLogger())

    await ui.run()

    assert len(FakePlayScreen.instances) == 1
    assert FakeGameScreen.instances == []


@pytest.mark.asyncio
async def test_play_flow_with_match_starts_game(monkeypatch):
    monkeypatch.setattr(shell_ui_module, "PlayScreen", FakePlayScreen)
    monkeypatch.setattr(shell_ui_module, "GameScreen", FakeGameScreen)

    class MatchedPlayScreen(FakePlayScreen):
        async def run(self):
            return {"game_id": "g1", "color": "w", "opponent": "bob"}

    monkeypatch.setattr(shell_ui_module, "PlayScreen", MatchedPlayScreen)
    _choices(monkeypatch, "3", "5")
    ui = ShellUI(FakeSession(authenticated=True), FakeClientLogger())

    await ui.run()

    assert len(FakeGameScreen.instances) == 1
    assert FakeGameScreen.instances[0].ran is True
    assert FakeGameScreen.instances[0].kwargs["game_id"] == "g1"


@pytest.mark.asyncio
async def test_room_blocked_when_not_logged_in(monkeypatch, capsys):
    _choices(monkeypatch, "4", "5")
    ui = ShellUI(FakeSession(authenticated=False), FakeClientLogger())

    await ui.run()

    assert "must be logged in" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_room_create_flow_invalid_submenu_choice(monkeypatch, capsys):
    monkeypatch.setattr(shell_ui_module, "RoomScreen", FakeRoomScreen)
    _choices(monkeypatch, "4", "9", "5")
    ui = ShellUI(FakeSession(authenticated=True), FakeClientLogger())

    await ui.run()

    assert "Invalid choice." in capsys.readouterr().out


@pytest.mark.asyncio
async def test_room_create_flow_starts_game_on_success(monkeypatch):
    monkeypatch.setattr(shell_ui_module, "GameScreen", FakeGameScreen)

    class CreatedRoomScreen(FakeRoomScreen):
        async def run_create(self):
            return {"game_id": "g1", "color": "w", "opponent": "bob", "room_id": "ABC123"}

    monkeypatch.setattr(shell_ui_module, "RoomScreen", CreatedRoomScreen)
    _choices(monkeypatch, "4", "1", "5")
    ui = ShellUI(FakeSession(authenticated=True), FakeClientLogger())

    await ui.run()

    assert len(FakeGameScreen.instances) == 1
    assert FakeGameScreen.instances[0].kwargs["room_id"] == "ABC123"


@pytest.mark.asyncio
async def test_room_join_flow_no_start_data_returns_to_menu(monkeypatch):
    monkeypatch.setattr(shell_ui_module, "RoomScreen", FakeRoomScreen)
    monkeypatch.setattr(shell_ui_module, "GameScreen", FakeGameScreen)
    _choices(monkeypatch, "4", "2", "5")
    ui = ShellUI(FakeSession(authenticated=True), FakeClientLogger())

    await ui.run()

    assert len(FakeRoomScreen.instances) == 1
    assert FakeGameScreen.instances == []


@pytest.mark.asyncio
async def test_login_and_register_choices_delegate_to_login_screen(monkeypatch):
    calls = []

    class FakeLoginScreen:
        def __init__(self, session):
            pass

        async def run_login(self):
            calls.append("login")
            return False

        async def run_register(self):
            calls.append("register")
            return False

    monkeypatch.setattr(shell_ui_module, "LoginScreen", FakeLoginScreen)
    _choices(monkeypatch, "1", "2", "5")
    ui = ShellUI(FakeSession(), FakeClientLogger())

    await ui.run()

    assert calls == ["login", "register"]


@pytest.mark.asyncio
async def test_logs_every_menu_choice():
    class Session(FakeSession):
        pass

    logger = FakeClientLogger()
    ui = ShellUI(Session(), logger)
    import builtins
    original_input = builtins.input
    choices = iter(["5"])
    builtins.input = lambda prompt="": next(choices)
    try:
        await ui.run()
    finally:
        builtins.input = original_input

    assert logger.actions == [("menu_choice", {"choice": "5"})]
