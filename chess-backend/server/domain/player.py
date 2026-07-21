"""
player.py — Player value object. No I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Player:
    user_id: int
    username: str
    elo: int
    conn_id: str
    session_token: str
