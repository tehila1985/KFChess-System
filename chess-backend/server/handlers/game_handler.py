"""
game_handler.py — handles MOVE and RESIGN messages → GameSession.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from common.protocol.message_types import MessageType
from common.protocol.schemas import (
    Envelope, MovePayload, MoveAckPayload, ResignPayload, ErrorPayload,
)
from server.services.game_session import GameSession
from server.services.auth_service import AuthService
from server.connection_hub import ConnectionHub
from server.domain.enums import GameResult, EndReason


class GameHandler:
    """
    Handles in-game messages from players.

    Looks up the active GameSession for the connection, then delegates.
    """

    def __init__(
        self,
        hub: ConnectionHub,
        auth_service: AuthService,
        logger: logging.Logger,
    ) -> None:
        self._hub = hub
        self._auth = auth_service
        self._log = logger
        # game_id → GameSession
        self._sessions: Dict[str, GameSession] = {}
        # conn_id → game_id
        self._conn_to_game: Dict[str, str] = {}

    def register_session(self, session: GameSession) -> None:
        """Called by MatchmakingService / RoomService after session creation."""
        self._sessions[session.game_id] = session
        self._conn_to_game[session.white.conn_id] = session.game_id
        self._conn_to_game[session.black.conn_id] = session.game_id

    def unregister_session(self, game_id: str) -> None:
        session = self._sessions.pop(game_id, None)
        if session:
            self._conn_to_game.pop(session.white.conn_id, None)
            self._conn_to_game.pop(session.black.conn_id, None)

    def get_session_by_conn(self, conn_id: str) -> Optional[GameSession]:
        game_id = self._conn_to_game.get(conn_id)
        if game_id is None:
            return None
        return self._sessions.get(game_id)

    async def handle_move(self, conn_id: str, envelope: Envelope) -> None:
        try:
            payload = MovePayload(**envelope.payload)
        except Exception:
            await self._send_error(conn_id, envelope.request_id, "invalid_payload")
            return

        # Validate token
        info = self._auth.validate_token(payload.session_token)
        if info is None:
            await self._send_error(conn_id, envelope.request_id, "unauthorized")
            return

        session = self.get_session_by_conn(conn_id)
        if session is None:
            await self._send_error(conn_id, envelope.request_id, "no_active_game")
            return

        result = await session.apply_move(
            conn_id,
            payload.src_row, payload.src_col,
            payload.dst_row, payload.dst_col,
        )

        ack = Envelope(
            type=MessageType.MOVE_ACK,
            request_id=envelope.request_id,
            payload=MoveAckPayload(
                src_row=payload.src_row, src_col=payload.src_col,
                dst_row=payload.dst_row, dst_col=payload.dst_col,
                status="accepted" if result.accepted else "rejected",
                reason=result.reason,
            ).model_dump(),
        )
        await self._hub.send(conn_id, ack.to_json())

    async def handle_resign(self, conn_id: str, envelope: Envelope) -> None:
        try:
            payload = ResignPayload(**envelope.payload)
        except Exception:
            await self._send_error(conn_id, envelope.request_id, "invalid_payload")
            return

        info = self._auth.validate_token(payload.session_token)
        if info is None:
            await self._send_error(conn_id, envelope.request_id, "unauthorized")
            return

        session = self.get_session_by_conn(conn_id)
        if session is None:
            await self._send_error(conn_id, envelope.request_id, "no_active_game")
            return

        # Determine which player resigned
        if conn_id == session.white.conn_id:
            result = GameResult.BLACK_WINS
        else:
            result = GameResult.WHITE_WINS

        await session.end_game(result, EndReason.RESIGN)

    async def _send_error(self, conn_id: str, request_id: str, reason: str) -> None:
        err = Envelope(
            type=MessageType.ERROR,
            request_id=request_id,
            payload=ErrorPayload(reason=reason).model_dump(),
        )
        await self._hub.send(conn_id, err.to_json())

    def make_move_handler(self):
        async def _h(conn_id: str, env: Envelope):
            await self.handle_move(conn_id, env)
        return _h

    def make_resign_handler(self):
        async def _h(conn_id: str, env: Envelope):
            await self.handle_resign(conn_id, env)
        return _h
