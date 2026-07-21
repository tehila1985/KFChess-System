"""
logger_factory.py — builds structured JSON loggers for server and client.

DRY: one factory parameterized by log_path; no setup code duplicated between
server_logger and client_logger. Every service receives an injected logger —
never calls logging.getLogger() directly.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from typing import Optional


class JsonFormatter(logging.Formatter):
    """Formats each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # merge any extra fields passed via extra={}
        for key, val in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "id", "levelname", "levelno",
                "lineno", "message", "module", "msecs", "msg", "name",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName", "taskName",
            ):
                if not key.startswith("_"):
                    payload[key] = val
        return json.dumps(payload, default=str)


def build_logger(
    name: str,
    log_path: str,
    level: str = "INFO",
    rotate_max_bytes: int = 5_000_000,
    rotate_backups: int = 5,
) -> logging.Logger:
    """
    Build and return a logger that writes JSON lines to log_path.

    Args:
        name: Logger name (used for the 'logger' field in JSON output).
        log_path: Path to the rotating log file.
        level: Logging level string (e.g. 'INFO', 'DEBUG').
        rotate_max_bytes: Max bytes before rotation.
        rotate_backups: Number of backup files to keep.
    """
    logger = logging.getLogger(name)
    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = JsonFormatter()

    # File handler (rotating)
    os.makedirs(os.path.dirname(log_path), exist_ok=True) if os.path.dirname(log_path) else None
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=rotate_max_bytes,
        backupCount=rotate_backups,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


class LoggerFactory:
    """
    Factory for building named loggers with consistent config.

    Injected into server main and client main so both use the same setup.
    """

    def __init__(
        self,
        level: str = "INFO",
        rotate_max_bytes: int = 5_000_000,
        rotate_backups: int = 5,
    ) -> None:
        self._level = level
        self._rotate_max_bytes = rotate_max_bytes
        self._rotate_backups = rotate_backups

    def get_server_logger(self, log_path: str) -> logging.Logger:
        return build_logger(
            "chess.server",
            log_path,
            self._level,
            self._rotate_max_bytes,
            self._rotate_backups,
        )

    def get_client_logger(self, log_path: str) -> logging.Logger:
        return build_logger(
            "chess.client",
            log_path,
            self._level,
            self._rotate_max_bytes,
            self._rotate_backups,
        )

    def get_named_logger(self, name: str, log_path: str) -> logging.Logger:
        return build_logger(
            name,
            log_path,
            self._level,
            self._rotate_max_bytes,
            self._rotate_backups,
        )
