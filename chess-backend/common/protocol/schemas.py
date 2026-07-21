"""
schemas.py — pydantic models for every message payload.

Validated on receipt so no handler silently depends on undocumented dict shapes.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field

from common.protocol.message_types import MessageType


# ── Envelope ─────────────────────────────────────────────────────────────────

class Envelope(BaseModel):
    """Top-level message wrapper for every client↔server message."""
    type: MessageType
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "Envelope":
        return cls.model_validate_json(raw)


# ── Auth payloads ─────────────────────────────────────────────────────────────

class LoginPayload(BaseModel):
    username: str
    password: str


class RegisterPayload(BaseModel):
    username: str
    password: str


class LoginOkPayload(BaseModel):
    session_token: str
    elo: int
    username: str


class LoginErrorPayload(BaseModel):
    reason: str


class RegisterOkPayload(BaseModel):
    username: str


class RegisterErrorPayload(BaseModel):
    reason: str


# ── Play payloads ─────────────────────────────────────────────────────────────

class PlayRequestPayload(BaseModel):
    session_token: str


class PlaySearchingPayload(BaseModel):
    elapsed_seconds: float


class PlayMatchFoundPayload(BaseModel):
    opponent: str
    color: str  # 'w' or 'b'
    game_id: str


class PlayTimeoutPayload(BaseModel):
    reason: str = "no_opponent_found"


# ── Room payloads ─────────────────────────────────────────────────────────────

class RoomCreatePayload(BaseModel):
    session_token: str


class RoomJoinPayload(BaseModel):
    session_token: str
    room_id: str


class RoomCreatedPayload(BaseModel):
    room_id: str


class RoomJoinedPayload(BaseModel):
    room_id: str
    role: str


class RoomRoleAssignedPayload(BaseModel):
    role: str


class RoomErrorPayload(BaseModel):
    reason: str


# ── Game payloads ─────────────────────────────────────────────────────────────

class GameStartPayload(BaseModel):
    game_id: str
    color: str  # 'w' or 'b'
    opponent: str
    room_id: Optional[str] = None


class MovePayload(BaseModel):
    session_token: str
    src_row: int
    src_col: int
    dst_row: int
    dst_col: int


class MoveAckPayload(BaseModel):
    src_row: int
    src_col: int
    dst_row: int
    dst_col: int
    status: str  # 'accepted' | 'rejected'
    reason: Optional[str] = None


class MoveBroadcastPayload(BaseModel):
    src_row: int
    src_col: int
    dst_row: int
    dst_col: int
    color: str


class GameEndPayload(BaseModel):
    result: str   # 'white' | 'black' | 'draw' | 'aborted'
    reason: str   # 'checkmate' | 'resign' | 'disconnect_timeout' | ...
    white_elo_before: int
    black_elo_before: int
    white_elo_after: int
    black_elo_after: int


class OpponentDisconnectedPayload(BaseModel):
    username: str


class DisconnectCountdownTickPayload(BaseModel):
    seconds_left: int


class ResignPayload(BaseModel):
    session_token: str


# ── System payloads ───────────────────────────────────────────────────────────

class PingPayload(BaseModel):
    pass


class PongPayload(BaseModel):
    pass


class ErrorPayload(BaseModel):
    reason: str
    code: Optional[str] = None
