"""
config_loader.py — loads config/default.yaml into a typed Settings object.

Rules:
- Loaded exactly once at startup, then injected into every service.
- No service reads from disk on a hot path.
- No raw numbers or strings in business logic — all tunables live in default.yaml.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass(frozen=True)
class RatingSettings:
    starting_elo: int
    k_factor: int
    match_range: int


@dataclass(frozen=True)
class MatchmakingSettings:
    queue_timeout_seconds: int
    poll_interval_seconds: float


@dataclass(frozen=True)
class GameSettings:
    disconnect_grace_seconds: int
    countdown_tick_seconds: float


@dataclass(frozen=True)
class RoomSettings:
    id_length: int
    id_alphabet: str


@dataclass(frozen=True)
class AuthSettings:
    password_hash_scheme: str
    min_password_length: int
    session_token_ttl_seconds: int


@dataclass(frozen=True)
class ServerSettings:
    host: str
    port: int
    db_path: str


@dataclass(frozen=True)
class LoggingSettings:
    server_log_path: str
    client_log_path: str
    level: str
    rotate_max_bytes: int
    rotate_backups: int


@dataclass(frozen=True)
class Settings:
    rating: RatingSettings
    matchmaking: MatchmakingSettings
    game: GameSettings
    room: RoomSettings
    auth: AuthSettings
    server: ServerSettings
    logging: LoggingSettings


def load_settings(config_path: Optional[str] = None) -> Settings:
    """
    Load settings from a YAML config file.

    Args:
        config_path: Path to the YAML file. Defaults to config/default.yaml
                     relative to the chess-backend directory.
    """
    if config_path is None:
        base = Path(__file__).parent.parent
        config_path = str(base / "config" / "default.yaml")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    r = raw["rating"]
    m = raw["matchmaking"]
    g = raw["game"]
    ro = raw["room"]
    a = raw["auth"]
    s = raw["server"]
    lo = raw["logging"]

    return Settings(
        rating=RatingSettings(
            starting_elo=r["starting_elo"],
            k_factor=r["k_factor"],
            match_range=r["match_range"],
        ),
        matchmaking=MatchmakingSettings(
            queue_timeout_seconds=m["queue_timeout_seconds"],
            poll_interval_seconds=m["poll_interval_seconds"],
        ),
        game=GameSettings(
            disconnect_grace_seconds=g["disconnect_grace_seconds"],
            countdown_tick_seconds=g["countdown_tick_seconds"],
        ),
        room=RoomSettings(
            id_length=ro["id_length"],
            id_alphabet=ro["id_alphabet"],
        ),
        auth=AuthSettings(
            password_hash_scheme=a["password_hash_scheme"],
            min_password_length=a["min_password_length"],
            session_token_ttl_seconds=a["session_token_ttl_seconds"],
        ),
        server=ServerSettings(
            host=s["host"],
            port=s["port"],
            db_path=s["db_path"],
        ),
        logging=LoggingSettings(
            server_log_path=lo["server_log_path"],
            client_log_path=lo["client_log_path"],
            level=lo["level"],
            rotate_max_bytes=lo["rotate_max_bytes"],
            rotate_backups=lo["rotate_backups"],
        ),
    )
