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
                print("Play feature coming soon.")
            elif choice == "4":
                if not require_login(self._session):
                    continue
                print("Room feature coming soon.")
            elif choice == "5":
                print("Goodbye.")
                break
            else:
                print("Invalid choice.")
