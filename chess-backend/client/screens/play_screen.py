"""
play_screen.py — shows searching state + countdown, handles match found.

SRP: presentation only.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, PlayRequestPayload


class PlayScreen:
    """
    Renders the matchmaking search state.

    Displays elapsed time while searching.
    Shows 'Match found!' and transitions to GameScreen on PLAY_MATCH_FOUND.
    Shows timeout popup on PLAY_TIMEOUT.
    """

    def __init__(self, session) -> None:
        self._session = session
        self._match_found: Optional[dict] = None
        self._timed_out = False

    def on_match_found(self, env: Envelope) -> None:
        self._match_found = env.payload

    def on_timeout(self, env: Envelope) -> None:
        self._timed_out = True

    async def run(self) -> Optional[dict]:
        """
        Enqueue for matchmaking, display progress, and return match data when found.

        Returns the match payload dict (with game_id, color, opponent) or None on timeout.
        """
        self._session.on(MessageType.PLAY_MATCH_FOUND, self.on_match_found)
        self._session.on(MessageType.PLAY_TIMEOUT, self.on_timeout)

        env = Envelope(
            type=MessageType.PLAY_REQUEST,
            payload=PlayRequestPayload(
                session_token=self._session.session_token
            ).model_dump(),
        )
        await self._session.send(env)

        print("Searching for opponent...")
        start = time.monotonic()

        while not self._match_found and not self._timed_out:
            elapsed = int(time.monotonic() - start)
            print(f"\rSearching... {elapsed}s elapsed", end="", flush=True)
            await asyncio.sleep(1.0)

        print()  # newline after the searching line
        if self._match_found:
            m = self._match_found
            print(f"Match found! You are {'White' if m['color'] == 'w' else 'Black'} vs {m['opponent']}")
            return self._match_found
        else:
            print("Could not find an opponent. Returning to menu.")
            return None
