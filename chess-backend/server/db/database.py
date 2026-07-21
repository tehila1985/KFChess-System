"""
database.py — SQLite connection factory and schema initializer.

Provides a single function to get a connected, schema-initialized database.
All SQL is kept in schema.sql — no inline DDL in application code.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Open (or create) an SQLite database at db_path, apply schema, return connection.

    Uses WAL mode for better concurrency and row_factory for named column access.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True) if os.path.dirname(db_path) else None
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _apply_schema(conn)
    return conn


def _apply_schema(conn: sqlite3.Connection) -> None:
    """Apply schema.sql if tables don't exist yet."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    conn.commit()
