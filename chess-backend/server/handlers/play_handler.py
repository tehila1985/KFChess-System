"""
play_handler.py — handles PLAY_REQUEST and PLAY_CANCEL → MatchmakingService.
"""
from __future__ import annotations

import logging
from typing import Any

from common.protocol.message_types import MessageType
from common.protocol.schemas import (
    Envelope, PlayRequestPayload, PlaySearchingPayload, ErrorPayload,
)
from server.services.matchmaking_service import MatchmakingService
from server.services.auth_service import AuthService
from server.domain.player import Player
from server.connection_hub import ConnectionHub
from server.repositories.base_repository import AbstractUserRepository


class PlayHandler:
    """Handles play request and cancel messages."""

    def __init__(
        self,
        matchmaking: MatchmakingService,
        auth_service: AuthService,
        user_repo: AbstractUserRepository,
        hub: ConnectionHub,
        logger: logging.Logger,
    ) -> None:
        self._mm = matchmaking
        self._auth = auth_service
        self._user_repo = user_repo
        self._hub = hub
        self._log = logger

    async def handle_play_request(self, conn_id: str, envelope: Envelope) -> None:
        try:
            payload = PlayRequestPayload(**envelope.payload)
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
        self._mm.enqueue(player)

        # Acknowledge with PLAY_SEARCHING
        resp = Envelope(
            type=MessageType.PLAY_SEARCHING,
            request_id=envelope.request_id,
            payload=PlaySearchingPayload(elapsed_seconds=0.0).model_dump(),
        )
        await self._hub.send(conn_id, resp.to_json())

    async def handle_play_cancel(self, conn_id: str, envelope: Envelope) -> None:
        self._mm.dequeue(conn_id)
        self._log.info("play_cancel conn_id=%s", conn_id)

    async def _send_error(self, conn_id: str, request_id: str, reason: str) -> None:
        err = Envelope(
            type=MessageType.ERROR,
            request_id=request_id,
            payload=ErrorPayload(reason=reason).model_dump(),
        )
        await self._hub.send(conn_id, err.to_json())

    def make_play_request_handler(self):
        async def _h(conn_id: str, env: Envelope):
            await self.handle_play_request(conn_id, env)
        return _h

    def make_play_cancel_handler(self):
        async def _h(conn_id: str, env: Envelope):
            await self.handle_play_cancel(conn_id, env)
        return _h
