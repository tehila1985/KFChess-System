"""
message_types.py — single source of truth for all message type strings.

All message type values used on the wire are defined here as enum members.
No handler or service may use raw string literals for message types.
"""
from enum import Enum


class MessageType(str, Enum):
    # ── Auth ──────────────────────────────────────────────────────────
    LOGIN = "LOGIN"
    REGISTER = "REGISTER"
    LOGIN_OK = "LOGIN_OK"
    LOGIN_ERROR = "LOGIN_ERROR"
    REGISTER_OK = "REGISTER_OK"
    REGISTER_ERROR = "REGISTER_ERROR"

    # ── Play (matchmaking) ────────────────────────────────────────────
    PLAY_REQUEST = "PLAY_REQUEST"
    PLAY_CANCEL = "PLAY_CANCEL"
    PLAY_SEARCHING = "PLAY_SEARCHING"
    PLAY_MATCH_FOUND = "PLAY_MATCH_FOUND"
    PLAY_TIMEOUT = "PLAY_TIMEOUT"

    # ── Room ──────────────────────────────────────────────────────────
    ROOM_CREATE = "ROOM_CREATE"
    ROOM_JOIN = "ROOM_JOIN"
    ROOM_CREATED = "ROOM_CREATED"
    ROOM_JOINED = "ROOM_JOINED"
    ROOM_ERROR = "ROOM_ERROR"
    ROOM_ROLE_ASSIGNED = "ROOM_ROLE_ASSIGNED"

    # ── Game ──────────────────────────────────────────────────────────
    GAME_START = "GAME_START"
    MOVE = "MOVE"
    MOVE_ACK = "MOVE_ACK"
    MOVE_BROADCAST = "MOVE_BROADCAST"
    GAME_END = "GAME_END"
    OPPONENT_DISCONNECTED = "OPPONENT_DISCONNECTED"
    DISCONNECT_COUNTDOWN_TICK = "DISCONNECT_COUNTDOWN_TICK"
    AUTO_RESIGN = "AUTO_RESIGN"
    RESIGN = "RESIGN"
    GAME_STATE = "GAME_STATE"

    # ── System ────────────────────────────────────────────────────────
    PING = "PING"
    PONG = "PONG"
    ERROR = "ERROR"
