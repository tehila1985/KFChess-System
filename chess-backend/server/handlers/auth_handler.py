"""
auth_handler.py — handles LOGIN and REGISTER messages.

Delegates all business logic to AuthService.
"""
from __future__ import annotations

import logging
from typing import Any

from common.protocol.message_types import MessageType
from common.protocol.schemas import (
    Envelope,
    LoginPayload,
    LoginOkPayload,
    LoginErrorPayload,
    RegisterPayload,
    RegisterOkPayload,
    RegisterErrorPayload,
)
from server.services.auth_service import AuthService, AuthSuccess, AuthError
from server.connection_hub import ConnectionHub


class AuthHandler:
    """
    Processes auth messages from the router.

    Constructor parameters (DI): AuthService, ConnectionHub, logger.
    """

    def __init__(
        self,
        auth_service: AuthService,
        hub: ConnectionHub,
        logger: logging.Logger,
    ) -> None:
        self._auth = auth_service
        self._hub = hub
        self._log = logger

    async def handle_login(self, conn_id: str, envelope: Envelope) -> None:
        self._log.info("auth_attempt action=login conn_id=%s", conn_id)
        try:
            payload = LoginPayload(**envelope.payload)
        except Exception:
            await self._send_error(conn_id, envelope.request_id, "invalid_payload")
            return

        result = self._auth.login(payload.username, payload.password)
        if isinstance(result, AuthSuccess):
            self._hub.associate_token(conn_id, result.session_token)
            resp = Envelope(
                type=MessageType.LOGIN_OK,
                request_id=envelope.request_id,
                payload=LoginOkPayload(
                    session_token=result.session_token,
                    elo=result.elo,
                    username=result.username,
                ).model_dump(),
            )
            self._log.info("auth_success action=login username=%s", payload.username)
        else:
            resp = Envelope(
                type=MessageType.LOGIN_ERROR,
                request_id=envelope.request_id,
                payload=LoginErrorPayload(reason=result.reason).model_dump(),
            )
            self._log.warning("auth_failure action=login username=%s reason=%s",
                               payload.username, result.reason)

        await self._hub.send(conn_id, resp.to_json())

    async def handle_register(self, conn_id: str, envelope: Envelope) -> None:
        self._log.info("auth_attempt action=register conn_id=%s", conn_id)
        try:
            payload = RegisterPayload(**envelope.payload)
        except Exception:
            await self._send_error(conn_id, envelope.request_id, "invalid_payload")
            return

        result = self._auth.register(payload.username, payload.password)
        if isinstance(result, AuthSuccess):
            self._hub.associate_token(conn_id, result.session_token)
            resp = Envelope(
                type=MessageType.REGISTER_OK,
                request_id=envelope.request_id,
                payload=RegisterOkPayload(username=result.username).model_dump(),
            )
            self._log.info("auth_success action=register username=%s", payload.username)
        else:
            resp = Envelope(
                type=MessageType.REGISTER_ERROR,
                request_id=envelope.request_id,
                payload=RegisterErrorPayload(reason=result.reason).model_dump(),
            )
            self._log.warning("auth_failure action=register username=%s reason=%s",
                               payload.username, result.reason)

        await self._hub.send(conn_id, resp.to_json())

    async def _send_error(self, conn_id: str, request_id: str, reason: str) -> None:
        err = Envelope(
            type=MessageType.ERROR,
            request_id=request_id,
            payload={"reason": reason},
        )
        await self._hub.send(conn_id, err.to_json())

    def make_login_handler(self):
        async def _h(conn_id: str, env: Envelope):
            await self.handle_login(conn_id, env)
        return _h

    def make_register_handler(self):
        async def _h(conn_id: str, env: Envelope):
            await self.handle_register(conn_id, env)
        return _h
