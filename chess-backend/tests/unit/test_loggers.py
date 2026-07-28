"""
Unit tests for server/logging_/server_logger.py:ServerLogger and
client/logging_/client_logger.py:ClientLogger — the one-call-site-per-
event-category wrappers referenced throughout §11 of the implementation
plan. Each method is a thin, mechanical delegation to the underlying
stdlib logger; verified here against a MagicMock stand-in.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from server.logging_.server_logger import ServerLogger
from client.logging_.client_logger import ClientLogger


class TestServerLogger:
    def setup_method(self):
        self.raw = MagicMock()
        self.log = ServerLogger(self.raw)

    def test_connection_opened(self):
        self.log.connection_opened("c1", "127.0.0.1:1234")
        self.raw.info.assert_called_with("connection_opened", extra={"conn_id": "c1", "remote": "127.0.0.1:1234"})

    def test_connection_closed(self):
        self.log.connection_closed("c1", "127.0.0.1:1234")
        self.raw.info.assert_called_with("connection_closed", extra={"conn_id": "c1", "remote": "127.0.0.1:1234"})

    def test_auth_attempt(self):
        self.log.auth_attempt("login", "alice")
        self.raw.info.assert_called_with("auth_attempt", extra={"action": "login", "username": "alice"})

    def test_auth_success(self):
        self.log.auth_success("register", "bob")
        self.raw.info.assert_called_with("auth_success", extra={"action": "register", "username": "bob"})

    def test_auth_failure_uses_warning_and_never_logs_a_password_field(self):
        self.log.auth_failure("login", "alice", "bad_password")
        args, kwargs = self.raw.warning.call_args
        assert args[0] == "auth_failure"
        assert kwargs["extra"] == {"action": "login", "username": "alice", "reason": "bad_password"}
        assert "password" not in kwargs["extra"]

    def test_matchmaking_enqueue(self):
        self.log.matchmaking_enqueue("alice", 1200)
        self.raw.info.assert_called_with("matchmaking_enqueue", extra={"username": "alice", "elo": 1200})

    def test_matchmaking_timeout(self):
        self.log.matchmaking_timeout("alice")
        self.raw.info.assert_called_with("matchmaking_timeout", extra={"username": "alice"})

    def test_matchmaking_match(self):
        self.log.matchmaking_match("alice", "bob", "g1")
        self.raw.info.assert_called_with("matchmaking_match", extra={"white": "alice", "black": "bob", "game_id": "g1"})

    def test_room_created(self):
        self.log.room_created("ABC123", "alice")
        self.raw.info.assert_called_with("room_created", extra={"room_id": "ABC123", "owner": "alice"})

    def test_room_joined(self):
        self.log.room_joined("ABC123", "bob", "black")
        self.raw.info.assert_called_with("room_joined", extra={"room_id": "ABC123", "username": "bob", "role": "black"})

    def test_game_started(self):
        self.log.game_started("g1", "alice", "bob")
        self.raw.info.assert_called_with("game_started", extra={"game_id": "g1", "white": "alice", "black": "bob"})

    def test_move_applied(self):
        self.log.move_applied("g1", "alice", "(6,4)", "(4,4)")
        self.raw.info.assert_called_with(
            "move_applied", extra={"game_id": "g1", "username": "alice", "src": "(6,4)", "dst": "(4,4)"}
        )

    def test_move_rejected_uses_warning(self):
        self.log.move_rejected("g1", "bob", "(1,4)", "(3,4)", "not_your_piece")
        args, kwargs = self.raw.warning.call_args
        assert args[0] == "move_rejected"
        assert kwargs["extra"]["reason"] == "not_your_piece"

    def test_game_ended(self):
        self.log.game_ended("g1", "white", "resign")
        self.raw.info.assert_called_with("game_ended", extra={"game_id": "g1", "result": "white", "reason": "resign"})

    def test_disconnect_detected_uses_warning(self):
        self.log.disconnect_detected("g1", "alice")
        self.raw.warning.assert_called_with("disconnect_detected", extra={"game_id": "g1", "username": "alice"})

    def test_countdown_tick(self):
        self.log.countdown_tick("g1", "alice", 15)
        self.raw.info.assert_called_with(
            "countdown_tick", extra={"game_id": "g1", "username": "alice", "seconds_left": 15}
        )

    def test_auto_resign_uses_warning(self):
        self.log.auto_resign("g1", "alice")
        self.raw.warning.assert_called_with("auto_resign", extra={"game_id": "g1", "username": "alice"})

    def test_reconnect(self):
        self.log.reconnect("g1", "alice")
        self.raw.info.assert_called_with("reconnect", extra={"game_id": "g1", "username": "alice"})

    def test_rating_updated(self):
        self.log.rating_updated("alice", 1200, 1216)
        self.raw.info.assert_called_with(
            "rating_updated", extra={"username": "alice", "elo_before": 1200, "elo_after": 1216}
        )

    def test_error_defaults_no_exc_info(self):
        self.log.error("boom")
        self.raw.error.assert_called_with("boom", exc_info=False, extra={})

    def test_error_with_exc_info_and_extra_kwargs(self):
        self.log.error("boom", exc_info=True, game_id="g1")
        self.raw.error.assert_called_with("boom", exc_info=True, extra={"game_id": "g1"})


class TestClientLogger:
    def setup_method(self):
        self.raw = MagicMock()
        self.log = ClientLogger(self.raw)

    def test_user_action_formats_kwargs_into_message(self):
        self.log.user_action("menu_choice", choice="3")
        args, _ = self.raw.info.call_args
        assert args[0] == "user_action action=%s %s"
        assert args[1] == "menu_choice"
        assert "choice=3" in args[2]

    def test_message_sent(self):
        self.log.message_sent("LOGIN", "req-1")
        self.raw.info.assert_called_with("message_sent type=%s request_id=%s", "LOGIN", "req-1")

    def test_message_received(self):
        self.log.message_received("LOGIN_OK", "req-1")
        self.raw.info.assert_called_with("message_received type=%s request_id=%s", "LOGIN_OK", "req-1")

    def test_connection_drop_uses_warning(self):
        self.log.connection_drop("closed by peer")
        self.raw.warning.assert_called_with("connection_drop reason=%s", "closed by peer")

    def test_reconnect_attempt(self):
        self.log.reconnect_attempt(2)
        self.raw.info.assert_called_with("reconnect_attempt attempt=%s", 2)

    def test_render_error_uses_error_level(self):
        self.log.render_error("game_screen", "KeyError")
        self.raw.error.assert_called_with("render_error screen=%s exc=%s", "game_screen", "KeyError")

    def test_info_passthrough(self):
        self.log.info("connected uri=%s", uri="ws://x")
        self.raw.info.assert_called_with("connected uri=%s", extra={"uri": "ws://x"})

    def test_warning_passthrough(self):
        self.log.warning("something", code=5)
        self.raw.warning.assert_called_with("something", extra={"code": 5})
