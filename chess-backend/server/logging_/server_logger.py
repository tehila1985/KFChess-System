"""
server_logger.py — structured server-side logger.

One call site per event category. Injected into services — never print().
Passwords are never logged.
"""
from __future__ import annotations

import logging
from typing import Optional

from server.logging_.logger_factory import LoggerFactory
from server.config_loader import Settings


class ServerLogger:
    """
    Structured event logger for the server.

    Wraps a stdlib logger and provides named methods for every §11 event
    category so log sites are consistent and searchable.
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._log = logger

    # ── Connection ────────────────────────────────────────────────────
    def connection_opened(self, conn_id: str, remote: str) -> None:
        self._log.info("connection_opened", extra={"conn_id": conn_id, "remote": remote})

    def connection_closed(self, conn_id: str, remote: str) -> None:
        self._log.info("connection_closed", extra={"conn_id": conn_id, "remote": remote})

    # ── Auth ──────────────────────────────────────────────────────────
    def auth_attempt(self, action: str, username: str) -> None:
        """Log a login or register attempt. Never logs password."""
        self._log.info("auth_attempt", extra={"action": action, "username": username})

    def auth_success(self, action: str, username: str) -> None:
        self._log.info("auth_success", extra={"action": action, "username": username})

    def auth_failure(self, action: str, username: str, reason: str) -> None:
        self._log.warning("auth_failure", extra={"action": action, "username": username, "reason": reason})

    # ── Matchmaking ───────────────────────────────────────────────────
    def matchmaking_enqueue(self, username: str, elo: int) -> None:
        self._log.info("matchmaking_enqueue", extra={"username": username, "elo": elo})

    def matchmaking_timeout(self, username: str) -> None:
        self._log.info("matchmaking_timeout", extra={"username": username})

    def matchmaking_match(self, white: str, black: str, game_id: str) -> None:
        self._log.info("matchmaking_match", extra={"white": white, "black": black, "game_id": game_id})

    # ── Room ──────────────────────────────────────────────────────────
    def room_created(self, room_id: str, owner: str) -> None:
        self._log.info("room_created", extra={"room_id": room_id, "owner": owner})

    def room_joined(self, room_id: str, username: str, role: str) -> None:
        self._log.info("room_joined", extra={"room_id": room_id, "username": username, "role": role})

    # ── Game ──────────────────────────────────────────────────────────
    def game_started(self, game_id: str, white: str, black: str) -> None:
        self._log.info("game_started", extra={"game_id": game_id, "white": white, "black": black})

    def move_applied(self, game_id: str, username: str, src: str, dst: str) -> None:
        self._log.info("move_applied", extra={"game_id": game_id, "username": username, "src": src, "dst": dst})

    def move_rejected(self, game_id: str, username: str, src: str, dst: str, reason: str) -> None:
        self._log.warning("move_rejected", extra={"game_id": game_id, "username": username, "src": src, "dst": dst, "reason": reason})

    def game_ended(self, game_id: str, result: str, reason: str) -> None:
        self._log.info("game_ended", extra={"game_id": game_id, "result": result, "reason": reason})

    # ── Disconnect ────────────────────────────────────────────────────
    def disconnect_detected(self, game_id: str, username: str) -> None:
        self._log.warning("disconnect_detected", extra={"game_id": game_id, "username": username})

    def countdown_tick(self, game_id: str, username: str, seconds_left: int) -> None:
        self._log.info("countdown_tick", extra={"game_id": game_id, "username": username, "seconds_left": seconds_left})

    def auto_resign(self, game_id: str, username: str) -> None:
        self._log.warning("auto_resign", extra={"game_id": game_id, "username": username})

    def reconnect(self, game_id: str, username: str) -> None:
        self._log.info("reconnect", extra={"game_id": game_id, "username": username})

    # ── Rating ────────────────────────────────────────────────────────
    def rating_updated(self, username: str, elo_before: int, elo_after: int) -> None:
        self._log.info("rating_updated", extra={"username": username, "elo_before": elo_before, "elo_after": elo_after})

    # ── Error ─────────────────────────────────────────────────────────
    def error(self, msg: str, exc_info: bool = False, **kwargs) -> None:
        self._log.error(msg, exc_info=exc_info, extra=kwargs)


def build_server_logger(settings: Settings) -> ServerLogger:
    """Convenience factory used by server main."""
    factory = LoggerFactory(
        level=settings.logging.level,
        rotate_max_bytes=settings.logging.rotate_max_bytes,
        rotate_backups=settings.logging.rotate_backups,
    )
    logger = factory.get_server_logger(settings.logging.server_log_path)
    return ServerLogger(logger)
