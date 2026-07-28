"""
Unit tests for the terminal client's screen classes
(client/screens/home_screen.py, login_screen.py, play_screen.py,
room_screen.py). All networking is faked; input()/print() are exercised
for real (input() via monkeypatch) since that's the actual code path a
real terminal session runs.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from client.screens.home_screen import HomeScreen, require_login
from client.screens.login_screen import LoginScreen
from client.screens.play_screen import PlayScreen
from client.screens.room_screen import RoomScreen
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope


class FakeSession:
    def __init__(self, request_response=None, authenticated=False,
                 username=None, elo=None):
        self.session_token = "tok-1"
        self._request_response = request_response
        self._authenticated = authenticated
        self.username = username
        self.elo = elo
        self.sent = []
        self._handlers = {}
        self.auth = None

    def is_authenticated(self):
        return self._authenticated

    def set_auth(self, token, username, elo):
        self.auth = (token, username, elo)

    def on(self, msg_type, handler):
        self._handlers[msg_type] = handler
        # Fire shortly after registration via the event loop's own timer —
        # simulates a server push arriving while the screen is awaiting it.
        loop = asyncio.get_event_loop()
        payload = self._fire_payloads.get(msg_type) if hasattr(self, "_fire_payloads") else None
        if payload is not None:
            loop.call_later(0.05, lambda: handler(Envelope(type=msg_type, payload=payload)))

    async def send(self, env):
        self.sent.append(env)

    async def request(self, env, timeout=10.0):
        self.sent.append(env)
        return self._request_response


# ── home_screen.py ──────────────────────────────────────────────────────────

def test_require_login_true_when_authenticated(capsys):
    session = FakeSession(authenticated=True)
    assert require_login(session) is True
    assert capsys.readouterr().out == ""


def test_require_login_false_prints_message(capsys):
    session = FakeSession(authenticated=False)
    assert require_login(session) is False
    assert "must be logged in" in capsys.readouterr().out


def test_home_screen_render_logged_out(capsys):
    screen = HomeScreen(FakeSession(authenticated=False))
    screen.render()
    out = capsys.readouterr().out
    assert "=== Chess ===" in out
    assert "5) Quit" in out


def test_home_screen_render_logged_in(capsys):
    screen = HomeScreen(FakeSession(authenticated=True, username="alice", elo=1250))
    screen.render()
    out = capsys.readouterr().out
    assert "alice" in out
    assert "1250" in out


def test_home_screen_get_choice(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "3")
    screen = HomeScreen(FakeSession())
    assert screen.get_choice() == "3"


# ── login_screen.py ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success_sets_auth(monkeypatch, capsys):
    inputs = iter(["alice", "secret123"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    session = FakeSession(request_response=Envelope(
        type=MessageType.LOGIN_OK,
        payload={"session_token": "t", "username": "alice", "elo": 1200},
    ))
    screen = LoginScreen(session)

    result = await screen.run_login()

    assert result is True
    assert session.auth == ("t", "alice", 1200)
    assert "Logged in as alice" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_login_failure_returns_false(monkeypatch, capsys):
    inputs = iter(["alice", "wrong"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    session = FakeSession(request_response=Envelope(
        type=MessageType.LOGIN_ERROR, payload={"reason": "invalid_credentials"},
    ))
    screen = LoginScreen(session)

    result = await screen.run_login()

    assert result is False
    assert session.auth is None
    assert "invalid_credentials" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_register_success(monkeypatch, capsys):
    inputs = iter(["bob", "password123"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    session = FakeSession(request_response=Envelope(
        type=MessageType.REGISTER_OK, payload={"username": "bob"},
    ))
    screen = LoginScreen(session)

    result = await screen.run_register()

    assert result is True
    assert "Registered as bob" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_register_failure(monkeypatch, capsys):
    inputs = iter(["bob", "short"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    session = FakeSession(request_response=Envelope(
        type=MessageType.REGISTER_ERROR, payload={"reason": "password_too_short"},
    ))
    screen = LoginScreen(session)

    result = await screen.run_register()

    assert result is False
    assert "password_too_short" in capsys.readouterr().out


# ── play_screen.py ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_play_screen_match_found_returns_game_start_payload(capsys):
    session = FakeSession()
    session._fire_payloads = {
        MessageType.PLAY_MATCH_FOUND: {"opponent": "bob", "color": "w", "game_id": "g1"},
        MessageType.GAME_START: {"game_id": "g1", "color": "w", "opponent": "bob"},
    }
    screen = PlayScreen(session)

    result = await asyncio.wait_for(screen.run(), timeout=3.0)

    assert result == {"game_id": "g1", "color": "w", "opponent": "bob"}
    assert "Match found" in capsys.readouterr().out
    assert session.sent[0].type == MessageType.PLAY_REQUEST


@pytest.mark.asyncio
async def test_play_screen_falls_back_to_match_found_if_game_start_never_arrives(capsys):
    # No GAME_START fire payload — PlayScreen must fall back to the
    # PLAY_MATCH_FOUND payload after its internal 5s wait elapses. Waits for
    # real here rather than faking asyncio.wait_for: that function is a
    # shared global, and patching it would also redirect the outer
    # asyncio.wait_for(...) guarding this test itself.
    session = FakeSession()
    session._fire_payloads = {
        MessageType.PLAY_MATCH_FOUND: {"opponent": "bob", "color": "b", "game_id": "g1"},
    }
    screen = PlayScreen(session)

    result = await asyncio.wait_for(screen.run(), timeout=7.0)

    assert result == {"opponent": "bob", "color": "b", "game_id": "g1"}


@pytest.mark.asyncio
async def test_play_screen_timeout_returns_none(capsys):
    session = FakeSession()
    session._fire_payloads = {MessageType.PLAY_TIMEOUT: {"reason": "no_opponent_found"}}
    screen = PlayScreen(session)

    result = await asyncio.wait_for(screen.run(), timeout=3.0)

    assert result is None
    assert "Could not find an opponent" in capsys.readouterr().out


# ── room_screen.py ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_room_create_success_waits_for_game_start(capsys):
    session = FakeSession(request_response=Envelope(
        type=MessageType.ROOM_CREATED, payload={"room_id": "ABC123"},
    ))
    session._fire_payloads = {MessageType.GAME_START: {"game_id": "g1", "room_id": "ABC123"}}
    screen = RoomScreen(session)

    result = await asyncio.wait_for(screen.run_create(), timeout=3.0)

    assert result == {"game_id": "g1", "room_id": "ABC123"}
    assert "ABC123" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_room_create_error_returns_none(capsys):
    session = FakeSession(request_response=Envelope(
        type=MessageType.ROOM_ERROR, payload={"reason": "boom"},
    ))
    screen = RoomScreen(session)

    result = await screen.run_create()

    assert result is None
    assert "boom" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_room_join_success(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "abc123")
    session = FakeSession(request_response=Envelope(
        type=MessageType.ROOM_ROLE_ASSIGNED, payload={"role": "black"},
    ))
    session._fire_payloads = {MessageType.GAME_START: {"game_id": "g1"}}
    screen = RoomScreen(session)

    result = await asyncio.wait_for(screen.run_join(), timeout=3.0)

    assert result == {"game_id": "g1"}
    join_env = session.sent[0]
    assert join_env.payload["room_id"] == "ABC123"  # uppercased
    assert "joined as: black" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_room_join_viewer_prints_spectator_notice(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "xyz999")
    session = FakeSession(request_response=Envelope(
        type=MessageType.ROOM_ROLE_ASSIGNED, payload={"role": "viewer"},
    ))
    session._fire_payloads = {MessageType.GAME_START: {"game_id": "g1"}}
    screen = RoomScreen(session)

    await asyncio.wait_for(screen.run_join(), timeout=3.0)

    assert "spectator" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_room_join_error_returns_none(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "badid1")
    session = FakeSession(request_response=Envelope(
        type=MessageType.ROOM_ERROR, payload={"reason": "room_not_found"},
    ))
    screen = RoomScreen(session)

    result = await screen.run_join()

    assert result is None
    assert "room_not_found" in capsys.readouterr().out
