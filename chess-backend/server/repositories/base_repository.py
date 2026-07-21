"""
base_repository.py — abstract interface for repositories.

Defines the contract that SQLite implementations satisfy, and that
test fakes also satisfy. Services depend only on this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class UserRecord:
    """Value object returned by UserRepository — never exposes raw DB rows."""
    id: int
    username: str
    password_hash: str
    elo: int
    created_at: str
    last_login_at: Optional[str]


@dataclass
class GameRecord:
    """Value object for a completed game."""
    id: int
    white_user_id: int
    black_user_id: int
    result: str
    end_reason: str
    white_elo_before: int
    black_elo_before: int
    white_elo_after: int
    black_elo_after: int
    room_id: Optional[str]
    started_at: str
    ended_at: Optional[str]


class AbstractUserRepository(ABC):
    @abstractmethod
    def create(self, username: str, password_hash: str, starting_elo: int) -> UserRecord: ...

    @abstractmethod
    def get_by_username(self, username: str) -> Optional[UserRecord]: ...

    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[UserRecord]: ...

    @abstractmethod
    def update_elo(self, user_id: int, new_elo: int) -> None: ...

    @abstractmethod
    def update_last_login(self, user_id: int) -> None: ...


class AbstractGameRepository(ABC):
    @abstractmethod
    def record_game(
        self,
        white_user_id: int,
        black_user_id: int,
        result: str,
        end_reason: str,
        white_elo_before: int,
        black_elo_before: int,
        white_elo_after: int,
        black_elo_after: int,
        room_id: Optional[str],
        started_at: str,
        ended_at: str,
    ) -> int: ...

    @abstractmethod
    def get_by_id(self, game_id: int) -> Optional[GameRecord]: ...
