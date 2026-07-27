"""
shell_ui.py — menus, input prompts, rendering.

SRP: presentation only. No networking code here.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from client.client_session import ClientSession
from client.screens.home_screen import HomeScreen, require_login
from client.screens.login_screen import LoginScreen
from client.screens.play_screen import PlayScreen
from client.screens.room_screen import RoomScreen
from client.screens.game_screen import GameScreen
from client.logging_.client_logger import ClientLogger


class ShellUI:
    """
    Top-level shell UI. Drives the home menu loop.
    All screen interactions delegate to screen classes.
    """

    def __init__(self, session: ClientSession, client_logger: ClientLogger) -> None:
        self._session = session
        self._log = client_logger
        self._home = HomeScreen(session)
        self._login_screen = LoginScreen(session)

    async def run(self) -> None:
        """Main UI loop."""
        while True:
            self._home.render()
            choice = self._home.get_choice()
            self._log.user_action("menu_choice", choice=choice)

            if choice == "1":
                await self._login_screen.run_login()
            elif choice == "2":
                await self._login_screen.run_register()
            elif choice == "3":
                if not require_login(self._session):
                    continue
                await self._run_play()
            elif choice == "4":
                if not require_login(self._session):
                    continue
                await self._run_room()
            elif choice == "5":
                print("Goodbye.")
                break
            else:
                print("Invalid choice.")

    async def _run_play(self) -> None:
        """Matchmaking flow: search, then hand off to GameScreen on match."""
        play_screen = PlayScreen(self._session)
        match = await play_screen.run()
        if match is None:
            return
        await self._run_game(match)

    async def _run_room(self) -> None:
        """Room flow: create or join, then hand off to GameScreen on start."""
        print("\n=== Room ===")
        print("1) Create room")
        print("2) Join room")
        choice = input("Choice: ").strip()

        room_screen = RoomScreen(self._session)
        if choice == "1":
            start_data = await room_screen.run_create()
        elif choice == "2":
            start_data = await room_screen.run_join()
        else:
            print("Invalid choice.")
            return

        if start_data is None:
            return
        await self._run_game(start_data)

    async def _run_game(self, start_data: dict) -> None:
        game = GameScreen(
            self._session,
            game_id=start_data["game_id"],
            color=start_data["color"],
            opponent=start_data["opponent"],
            room_id=start_data.get("room_id"),
            board=start_data.get("board"),
            scores=start_data.get("scores"),
            game_over=start_data.get("game_over", False),
            winner=start_data.get("winner"),
        )
        await game.run()
