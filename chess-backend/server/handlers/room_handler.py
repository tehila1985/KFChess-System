"""
room_handler.py — handles ROOM_CREATE and ROOM_JOIN → RoomService.
"""
from __future__ import annotations

import logging

from common.protocol.message_types import MessageType
from common.protocol.schemas import (
    Envelope, RoomCreatePayload, RoomJoinPayload,
    RoomCreatedPayload, RoomJoinedPayload, RoomRoleAssignedPayload,
    RoomErrorPayload, ErrorPayload,
)
from server.services.room_service import RoomService
from server.services.auth_service import AuthService
from server.domain.player import Player
from server.connection_hub import ConnectionHub
from server.repositories.base_repository import AbstractUserRepository


class RoomHandler:
    """Handles room lifecycle messages."""

    def __init__(
        self,
        room_service: RoomService,
        auth_service: AuthService,
        user_repo: AbstractUserRepository,
        hub: ConnectionHub,
        logger: logging.Logger,
    ) -> None:
        self._rooms = room_service
        self._auth = auth_service
        self._user_repo = user_repo
        self._hub = hub
        self._log = logger

    async def handle_room_create(self, conn_id: str, envelope: Envelope) -> None:
        try:
            payload = RoomCreatePayload(**envelope.payload)
        except Exception:
            await self._send_error(conn_id, envelope.request_id, "invalid_payload")
            return

        info = self._auth.validate_token(payload.session_token)
        if info is None:
            await self._send_error(conn_id, envelope.request_id, "unauthorized")
            return

        user_id, username, elo = info
        player = Player(user_id=user_id, username=username, elo=elo,
                        conn_id=conn_id, session_token=payload.session_token)

        room_id = self._rooms.create_room(player)
        resp = Envelope(
            type=MessageType.ROOM_CREATED,
            request_id=envelope.request_id,
            payload=RoomCreatedPayload(room_id=room_id).model_dump(),
        )
        await self._hub.send(conn_id, resp.to_json())

    async def handle_room_join(self, conn_id: str, envelope: Envelope) -> None:
        try:
            payload = RoomJoinPayload(**envelope.payload)
        except Exception:
            await self._send_error(conn_id, envelope.request_id, "invalid_payload")
            return

        info = self._auth.validate_token(payload.session_token)
        if info is None:
            await self._send_error(conn_id, envelope.request_id, "unauthorized")
            return

        user_id, username, elo = info
        player = Player(user_id=user_id, username=username, elo=elo,
                        conn_id=conn_id, session_token=payload.session_token)

        result = self._rooms.join_room(payload.room_id, player)
        if result is None:
            err_resp = Envelope(
                type=MessageType.ROOM_ERROR,
                request_id=envelope.request_id,
                payload=RoomErrorPayload(reason="room_not_found").model_dump(),
            )
            await self._hub.send(conn_id, err_resp.to_json())
            return

        # Send role assignment to this player
        role_resp = Envelope(
            type=MessageType.ROOM_ROLE_ASSIGNED,
            request_id=envelope.request_id,
            payload=RoomRoleAssignedPayload(role=result.role.value).model_dump(),
        )
        await self._hub.send(conn_id, role_resp.to_json())

        # If second player joined → start the game
        if result.game_started:
            await self._rooms.start_game_if_ready(payload.room_id)

    async def _send_error(self, conn_id: str, request_id: str, reason: str) -> None:
        err = Envelope(
            type=MessageType.ERROR,
            request_id=request_id,
            payload=ErrorPayload(reason=reason).model_dump(),
        )
        await self._hub.send(conn_id, err.to_json())

    def make_room_create_handler(self):
        async def _h(conn_id: str, env: Envelope):
            await self.handle_room_create(conn_id, env)
        return _h

    def make_room_join_handler(self):
        async def _h(conn_id: str, env: Envelope):
            await self.handle_room_join(conn_id, env)
        return _h
