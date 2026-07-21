"""
game_screen.py — renders the active chess game in the terminal.

SRP: presentation only. Sends moves via ClientSession.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from common.protocol.message_types import MessageType
from common.protocol.schemas import Envelope, MovePayload, ResignPayload


class GameScreen:
    """
    Terminal chess game screen.

    Shows the board (text representation), handles move input,
    and renders disconnect countdown ticks.
    """

    def __init__(self, session, game_id: str, color: str, opponent: str,
                 room_id: Optional[str] = None) -> None:
        self._session = session
        self._game_id = game_id
        self._color = color
        self._opponent = opponent
        self._room_id = room_id
        self._board = None  # Last received board state
        self._game_over = False
        self._countdown: Optional[int] = None

    def on_move_broadcast(self, env: Envelope) -> None:
        p = env.payload
        print(f"  Move: ({p['src_row']},{p['src_col']}) → ({p['dst_row']},{p['dst_col']}) [{p['color']}]")

    def on_game_end(self, env: Envelope) -> None:
        p = env.payload
        print(f"\n=== Game Over ===")
        print(f"Result: {p['result']} | Reason: {p['reason']}")
        if self._color == 'w':
            print(f"Your ELO: {p['white_elo_before']} → {p['white_elo_after']}")
        else:
            print(f"Your ELO: {p['black_elo_before']} → {p['black_elo_after']}")
        self._game_over = True

    def on_opponent_disconnected(self, env: Envelope) -> None:
        print(f"\n{env.payload['username']} disconnected!")

    def on_countdown_tick(self, env: Envelope) -> None:
        self._countdown = env.payload['seconds_left']
        print(f"  Opponent reconnect countdown: {self._countdown}s remaining")

    def render_header(self) -> None:
        header = f"=== Game {self._game_id[:8]}... ==="
        if self._room_id:
            header = f"[Room: {self._room_id}] " + header
        print(header)
        print(f"You: {self._session.username} ({self._color}) vs {self._opponent}")

    async def run(self) -> None:
        """Run the game screen until the game ends."""
        # Register handlers for incoming game messages
        self._session.on(MessageType.MOVE_BROADCAST, self.on_move_broadcast)
        self._session.on(MessageType.GAME_END, self.on_game_end)
        self._session.on(MessageType.OPPONENT_DISCONNECTED, self.on_opponent_disconnected)
        self._session.on(MessageType.DISCONNECT_COUNTDOWN_TICK, self.on_countdown_tick)

        self.render_header()
        print("Game started. Enter moves as 'src_row src_col dst_row dst_col', or 'resign'.")

        while not self._game_over:
            try:
                raw = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("Move> ")
                )
                raw = raw.strip()
                if raw.lower() == "resign":
                    env = Envelope(
                        type=MessageType.RESIGN,
                        payload=ResignPayload(
                            session_token=self._session.session_token
                        ).model_dump(),
                    )
                    await self._session.send(env)
                    break
                parts = raw.split()
                if len(parts) == 4:
                    sr, sc, dr, dc = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                    env = Envelope(
                        type=MessageType.MOVE,
                        payload=MovePayload(
                            session_token=self._session.session_token,
                            src_row=sr, src_col=sc,
                            dst_row=dr, dst_col=dc,
                        ).model_dump(),
                    )
                    resp = await self._session.request(env)
                    if resp.payload.get("status") == "accepted":
                        print("  Move accepted.")
                    else:
                        print(f"  Move rejected: {resp.payload.get('reason', '?')}")
                else:
                    print("  Format: row col row col  (e.g. '6 4 4 4')")
            except (EOFError, KeyboardInterrupt):
                break
