"""
user_repository.py — SQLite-backed UserRepository.

All SQL lives here. No other module writes SQL for users.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from server.repositories.base_repository import AbstractUserRepository, UserRecord


class UserRepository(AbstractUserRepository):
    """
    Persists users to SQLite. Takes a connection as a constructor parameter (DI).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, username: str, password_hash: str, starting_elo: int) -> UserRecord:
        """
        Insert a new user. Raises ValueError if username already exists.
        """
        try:
            cur = self._conn.execute(
                "INSERT INTO users (username, password_hash, elo) VALUES (?, ?, ?)",
                (username, password_hash, starting_elo),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' already exists")

        user_id = cur.lastrowid
        return self.get_by_id(user_id)  # type: ignore[return-value]

    def get_by_username(self, username: str) -> Optional[UserRecord]:
        row = self._conn.execute(
            "SELECT id, username, password_hash, elo, created_at, last_login_at "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def get_by_id(self, user_id: int) -> Optional[UserRecord]:
        row = self._conn.execute(
            "SELECT id, username, password_hash, elo, created_at, last_login_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def update_elo(self, user_id: int, new_elo: int) -> None:
        self._conn.execute(
            "UPDATE users SET elo = ? WHERE id = ?",
            (new_elo, user_id),
        )
        self._conn.commit()

    def update_last_login(self, user_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (now, user_id),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_record(row) -> UserRecord:
        return UserRecord(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            elo=row["elo"],
            created_at=row["created_at"],
            last_login_at=row["last_login_at"],
        )
