"""
client_logger.py — structured client-side logger.

Logs user menu actions, messages sent/received (payload, not raw password),
render errors, and connection drops/reconnect attempts.
"""
from __future__ import annotations

import logging
from typing import Any, Optional


class ClientLogger:
    """Structured event logger for the chess CLI client."""

    def __init__(self, logger: logging.Logger) -> None:
        self._log = logger

    def user_action(self, action: str, **kwargs) -> None:
        self._log.info("user_action action=%s %s", action,
                       " ".join(f"{k}={v}" for k, v in kwargs.items()))

    def message_sent(self, msg_type: str, request_id: str) -> None:
        self._log.info("message_sent type=%s request_id=%s", msg_type, request_id)

    def message_received(self, msg_type: str, request_id: str) -> None:
        self._log.info("message_received type=%s request_id=%s", msg_type, request_id)

    def connection_drop(self, reason: str) -> None:
        self._log.warning("connection_drop reason=%s", reason)

    def reconnect_attempt(self, attempt: int) -> None:
        self._log.info("reconnect_attempt attempt=%s", attempt)

    def render_error(self, screen: str, exc: str) -> None:
        self._log.error("render_error screen=%s exc=%s", screen, exc)

    def info(self, msg: str, **kwargs) -> None:
        self._log.info(msg, extra=kwargs)

    def warning(self, msg: str, **kwargs) -> None:
        self._log.warning(msg, extra=kwargs)
