"""
enums.py — domain-level enumerations.

Used by services. No I/O here.
"""
from enum import Enum


class GameResult(str, Enum):
    WHITE_WINS = "white"
    BLACK_WINS = "black"
    DRAW = "draw"
    ABORTED = "aborted"


class RoomRole(str, Enum):
    WHITE = "white"
    BLACK = "black"
    VIEWER = "viewer"


class MatchStatus(str, Enum):
    SEARCHING = "searching"
    MATCHED = "matched"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class EndReason(str, Enum):
    CHECKMATE = "checkmate"
    RESIGN = "resign"
    DISCONNECT_TIMEOUT = "disconnect_timeout"
    DRAW_AGREEMENT = "draw_agreement"
    ABORTED = "aborted"
