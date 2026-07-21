"""
room_screen.py — create/join room and transition to game.

SRP: presentation only.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from common.protocol.message_types import MessageType
from common.protocol.schemas import (
    Envelope, RoomCreatePayload, RoomJoinPayload,
)


class RoomScreen:
    """
    Renders room create / join menus.

    Displays the room ID prominently at the top after creation.
    """

    def __init__(self, session) -> None:
        self._session = session

    async def run_create(self) -> Optional[dict]:
        """Create a room and display its ID. Returns game start data when opponent joins."""
        env = Envelope(
            type=MessageType.ROOM_CREATE,
            payload=RoomCreatePayload(
                session_token=self._session.session_token
            ).model_dump(),
        )
        resp = await self._session.request(env)
        if resp.type != MessageType.ROOM_CREATED:
            print(f"Error: {resp.payload.get('reason', 'unknown')}")
            return None

        room_id = resp.payload["room_id"]
        print(f"\n╔═══════════════════════╗")
        print(f"║  Room ID: {room_id:6}       ║")
        print(f"╚═══════════════════════╝")
        print("Waiting for opponent...")

        # Wait for GAME_START
        start_data = None
        self._session.on(MessageType.GAME_START, lambda e: self._on_game_start(e))
        self._game_start_event = asyncio.Event()
        self._game_start_payload = None

        await self._game_start_event.wait()
        return self._game_start_payload

    def _on_game_start(self, env: Envelope) -> None:
        self._game_start_payload = env.payload
        self._game_start_event.set()

    async def run_join(self) -> Optional[dict]:
        """Prompt for room ID, join the room."""
        room_id = input("Enter Room ID: ").strip().upper()
        env = Envelope(
            type=MessageType.ROOM_JOIN,
            payload=RoomJoinPayload(
                session_token=self._session.session_token,
                room_id=room_id,
            ).model_dump(),
        )
        resp = await self._session.request(env)
        if resp.type == MessageType.ROOM_ERROR:
            print(f"Error: {resp.payload.get('reason', 'unknown')}")
            return None

        role = resp.payload.get("role", "?")
        print(f"\n╔═══════════════════════╗")
        print(f"║  Room ID: {room_id:6}       ║")
        print(f"╚═══════════════════════╝")
        print(f"You joined as: {role}")

        if role == "viewer":
            print("You are a spectator.")

        # Wait for GAME_START
        self._session.on(MessageType.GAME_START, lambda e: self._on_game_start(e))
        self._game_start_event = asyncio.Event()
        self._game_start_payload = None
        await self._game_start_event.wait()
        return self._game_start_payload
