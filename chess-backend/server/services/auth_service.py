"""
auth_service.py — handles registration and login.

SRP: hashing/verification + delegates persistence to UserRepository.
Does NOT know about sockets, rooms, or games.
Passwords are NEVER logged.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from server.repositories.base_repository import AbstractUserRepository, UserRecord
from server.config_loader import Settings


@dataclass(frozen=True)
class AuthSuccess:
    session_token: str
    username: str
    elo: int
    user_id: int


@dataclass(frozen=True)
class AuthError:
    reason: str


# Active sessions: {session_token: (user_id, username, elo, expires_at)}
_sessions: dict[str, tuple[int, str, int, datetime]] = {}


def _new_token() -> str:
    return secrets.token_hex(32)


class AuthService:
    """
    Handles user registration and login.

    Constructor parameters (DI):
        repo: AbstractUserRepository — the only persistence layer this service touches.
        settings: Settings — config for min_password_length, starting_elo, token TTL.
        logger: logging.Logger — injected, never prints/logs passwords.
    """

    def __init__(
        self,
        repo: AbstractUserRepository,
        settings: Settings,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._log = logger or logging.getLogger(__name__)
        self._ph = PasswordHasher()

    def register(self, username: str, password: str) -> Union[AuthSuccess, AuthError]:
        """
        Register a new user.

        Returns AuthSuccess on success, AuthError on failure.
        Password is hashed (argon2) — never stored or logged in plaintext.
        """
        username = username.strip()
        if len(username) < 1:
            return AuthError("username_too_short")
        if len(password) < self._settings.auth.min_password_length:
            return AuthError(
                f"password_too_short_min_{self._settings.auth.min_password_length}"
            )
        if self._repo.get_by_username(username) is not None:
            return AuthError("username_taken")

        password_hash = self._ph.hash(password)
        try:
            user = self._repo.create(
                username=username,
                password_hash=password_hash,
                starting_elo=self._settings.rating.starting_elo,
            )
        except ValueError:
            return AuthError("username_taken")

        token = self._issue_token(user.id, user.username, user.elo)
        self._log.info("register_ok username=%s", username)
        return AuthSuccess(
            session_token=token,
            username=user.username,
            elo=user.elo,
            user_id=user.id,
        )

    def login(self, username: str, password: str) -> Union[AuthSuccess, AuthError]:
        """
        Authenticate an existing user.

        Returns AuthSuccess with a session token on success.
        """
        user = self._repo.get_by_username(username)
        if user is None:
            self._log.warning("login_fail reason=unknown_user username=%s", username)
            return AuthError("invalid_credentials")

        try:
            self._ph.verify(user.password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            self._log.warning("login_fail reason=bad_password username=%s", username)
            return AuthError("invalid_credentials")

        self._repo.update_last_login(user.id)
        token = self._issue_token(user.id, user.username, user.elo)
        self._log.info("login_ok username=%s", username)
        return AuthSuccess(
            session_token=token,
            username=user.username,
            elo=user.elo,
            user_id=user.id,
        )

    def validate_token(self, token: str) -> Optional[tuple[int, str, int]]:
        """
        Validate a session token.

        Returns (user_id, username, elo) if valid and not expired, else None.
        """
        entry = _sessions.get(token)
        if entry is None:
            return None
        user_id, username, elo, expires_at = entry
        if datetime.now(timezone.utc) > expires_at:
            _sessions.pop(token, None)
            return None
        return user_id, username, elo

    def _issue_token(self, user_id: int, username: str, elo: int) -> str:
        token = _new_token()
        ttl = self._settings.auth.session_token_ttl_seconds
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        _sessions[token] = (user_id, username, elo, expires_at)
        return token
