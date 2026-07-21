"""
game_repository.py — SQLite-backed GameRepository.

All SQL for games/moves lives here. No other module writes game SQL.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from server.repositories.base_repository import AbstractGameRepository, GameRecord


class GameRepository(AbstractGameRepository):
    """Persists game records to SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

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
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO games (
                white_user_id, black_user_id, result, end_reason,
                white_elo_before, black_elo_before, white_elo_after, black_elo_after,
                room_id, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                white_user_id, black_user_id, result, end_reason,
                white_elo_before, black_elo_before, white_elo_after, black_elo_after,
                room_id, started_at, ended_at,
            ),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_by_id(self, game_id: int) -> Optional[GameRecord]:
        row = self._conn.execute(
            "SELECT * FROM games WHERE id = ?", (game_id,)
        ).fetchone()
        if row is None:
            return None
        return GameRecord(
            id=row["id"],
            white_user_id=row["white_user_id"],
            black_user_id=row["black_user_id"],
            result=row["result"],
            end_reason=row["end_reason"],
            white_elo_before=row["white_elo_before"],
            black_elo_before=row["black_elo_before"],
            white_elo_after=row["white_elo_after"],
            black_elo_after=row["black_elo_after"],
            room_id=row["room_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )
