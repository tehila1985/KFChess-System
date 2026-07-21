"""
login_screen.py — handles login and register prompts.

SRP: presentation + input only. All networking goes through ClientSession.
"""
from __future__ import annotations

from typing import Optional

from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, LoginPayload, RegisterPayload


class LoginScreen:
    """
    Renders login/register prompts and submits auth requests via ClientSession.
    """

    def __init__(self, session) -> None:
        self._session = session

    async def run_login(self) -> bool:
        """
        Prompt for username/password and attempt login.
        Returns True on success, False on failure.
        """
        print("\n=== Login ===")
        username = input("Username: ").strip()
        password = input("Password: ").strip()

        env = Envelope(
            type=MessageType.LOGIN,
            payload=LoginPayload(username=username, password=password).model_dump(),
        )
        resp = await self._session.request(env)

        if resp.type == MessageType.LOGIN_OK:
            self._session.set_auth(
                resp.payload["session_token"],
                resp.payload["username"],
                resp.payload["elo"],
            )
            print(f"Logged in as {resp.payload['username']} (ELO: {resp.payload['elo']})")
            return True
        else:
            print(f"Login failed: {resp.payload.get('reason', 'unknown')}")
            return False

    async def run_register(self) -> bool:
        """
        Prompt for new username/password and attempt registration.
        Returns True on success.
        """
        print("\n=== Register ===")
        username = input("Username: ").strip()
        password = input("Password: ").strip()

        env = Envelope(
            type=MessageType.REGISTER,
            payload=RegisterPayload(username=username, password=password).model_dump(),
        )
        resp = await self._session.request(env)

        if resp.type == MessageType.REGISTER_OK:
            print(f"Registered as {resp.payload['username']}. Please login.")
            return True
        else:
            print(f"Registration failed: {resp.payload.get('reason', 'unknown')}")
            return False
