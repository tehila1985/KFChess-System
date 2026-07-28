"""
Unit tests for client/screens/game_screen.py (terminal board renderer).
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from client.screens.game_screen import GameScreen
from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope

_STARTING_BOARD = [
    ["bR", "bN", "bB", "bQ", "bK", "bB", "bN", "bR"],
    ["bP", "bP", "bP", "bP", "bP", "bP", "bP", "bP"],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    ["wP", "wP", "wP", "wP", "wP", "wP", "wP", "wP"],
    ["wR", "wN", "wB", "wQ", "wK", "wB", "wN", "wR"],
]


class FakeSession:
    def __init__(self, move_response=None):
        self.username = "alice"
        self.session_token = "tok-1"
        self._handlers = {}
        self.sent = []
        self._move_response = move_response

    def on(self, msg_type, handler):
        self._handlers[msg_type] = handler

    async def send(self, env):
        self.sent.append(env)

    async def request(self, env, timeout=10.0):
        self.sent.append(env)
        return self._move_response


def _screen(**kwargs):
    return GameScreen(FakeSession(), game_id="game-id-12345", color="w", opponent="bob", **kwargs)


def test_constructor_without_board_does_not_render(capsys):
    _screen()
    assert capsys.readouterr().out == ""


def test_constructor_with_board_renders_immediately(capsys):
    _screen(board=_STARTING_BOARD, scores={"w": 0, "b": 0})
    out = capsys.readouterr().out
    assert "wP" in out
    assert "Score" in out


def test_on_move_broadcast_prints_move_and_rerenders(capsys):
    screen = _screen()
    env = Envelope(type=MessageType.MOVE_BROADCAST, payload={
        "src_row": 6, "src_col": 4, "dst_row": 4, "dst_col": 4, "color": "w",
        "board": _STARTING_BOARD, "scores": {"w": 0, "b": 0}, "game_over": False, "winner": None,
    })
    screen.on_move_broadcast(env)
    out = capsys.readouterr().out
    assert "(6,4) -> (4,4)" in out
    assert "wP" in out


def test_on_game_end_white_shows_own_elo(capsys):
    screen = _screen()  # color='w'
    env = Envelope(type=MessageType.GAME_END, payload={
        "result": "white", "reason": "resign",
        "white_elo_before": 1200, "white_elo_after": 1216,
        "black_elo_before": 1200, "black_elo_after": 1184,
    })
    screen.on_game_end(env)
    out = capsys.readouterr().out
    assert "1200 -> 1216" in out
    assert screen._game_over is True


def test_on_game_end_black_shows_own_elo(capsys):
    screen = GameScreen(FakeSession(), game_id="g1", color="b", opponent="alice")
    env = Envelope(type=MessageType.GAME_END, payload={
        "result": "white", "reason": "checkmate",
        "white_elo_before": 1200, "white_elo_after": 1216,
        "black_elo_before": 1200, "black_elo_after": 1184,
    })
    screen.on_game_end(env)
    out = capsys.readouterr().out
    assert "1200 -> 1184" in out


def test_on_opponent_disconnected(capsys):
    screen = _screen()
    screen.on_opponent_disconnected(Envelope(type=MessageType.OPPONENT_DISCONNECTED, payload={"username": "bob"}))
    assert "bob disconnected" in capsys.readouterr().out


def test_on_countdown_tick(capsys):
    screen = _screen()
    screen.on_countdown_tick(Envelope(type=MessageType.DISCONNECT_COUNTDOWN_TICK, payload={"seconds_left": 12}))
    assert screen._countdown == 12
    assert "12s remaining" in capsys.readouterr().out


def test_render_header_without_room(capsys):
    screen = _screen()
    screen.render_header()
    out = capsys.readouterr().out
    assert "Game game-id-..." in out
    assert "alice (w) vs bob" in out
    assert "[Room:" not in out


def test_render_header_with_room(capsys):
    screen = _screen(room_id="ABC123")
    screen.render_header()
    assert "[Room: ABC123]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_resign_sends_resign_and_exits(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "resign")
    session = FakeSession()
    screen = GameScreen(session, game_id="g1", color="w", opponent="bob")

    await asyncio.wait_for(screen.run(), timeout=3.0)

    assert session.sent[0].type == MessageType.RESIGN
    assert MessageType.MOVE_BROADCAST in session._handlers


@pytest.mark.asyncio
async def test_run_accepted_move_then_resign(monkeypatch, capsys):
    inputs = iter(["6 4 4 4", "resign"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    session = FakeSession(move_response=Envelope(
        type=MessageType.MOVE_ACK, payload={"status": "accepted"},
    ))
    screen = GameScreen(session, game_id="g1", color="w", opponent="bob")

    await asyncio.wait_for(screen.run(), timeout=3.0)

    move_env = session.sent[0]
    assert move_env.type == MessageType.MOVE
    assert move_env.payload["src_row"] == 6
    assert "Move accepted" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_rejected_move_then_resign(monkeypatch, capsys):
    inputs = iter(["6 4 4 4", "resign"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    session = FakeSession(move_response=Envelope(
        type=MessageType.MOVE_ACK, payload={"status": "rejected", "reason": "piece_on_cooldown"},
    ))
    screen = GameScreen(session, game_id="g1", color="w", opponent="bob")

    await asyncio.wait_for(screen.run(), timeout=3.0)

    assert "Move rejected: piece_on_cooldown" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_invalid_format_then_resign(monkeypatch, capsys):
    inputs = iter(["nonsense", "resign"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    session = FakeSession()
    screen = GameScreen(session, game_id="g1", color="w", opponent="bob")

    await asyncio.wait_for(screen.run(), timeout=3.0)

    assert "Format: row col row col" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_eof_breaks_loop(monkeypatch, capsys):
    def _raise(prompt=""):
        raise EOFError()
    monkeypatch.setattr("builtins.input", _raise)
    session = FakeSession()
    screen = GameScreen(session, game_id="g1", color="w", opponent="bob")

    await asyncio.wait_for(screen.run(), timeout=3.0)

    assert session.sent == []
