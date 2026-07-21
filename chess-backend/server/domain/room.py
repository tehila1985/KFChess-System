"""
room.py — Room value object. No I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List

from server.domain.player import Player
from server.domain.enums import RoomRole


@dataclass
class Room:
    room_id: str
    owner: Player
    white: Optional[Player] = None
    black: Optional[Player] = None
    viewers: List[Player] = field(default_factory=list)
    game_id: Optional[str] = None

    def is_full(self) -> bool:
        """Returns True when both player slots are filled."""
        return self.white is not None and self.black is not None
