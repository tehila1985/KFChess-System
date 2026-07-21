"""
home_screen.py — main menu screen.

SRP: presentation and menu navigation only.
"""
from __future__ import annotations

from typing import Optional


def require_login(session) -> bool:
    """
    Single guard used by all screens that require authentication.
    Returns True if user is logged in, False otherwise.
    """
    if not session.is_authenticated():
        print("You must be logged in to do that. Please login first.")
        return False
    return True


class HomeScreen:
    """
    Top-level menu. Delegates to LoginScreen / PlayScreen / RoomScreen etc.
    """

    def __init__(self, session) -> None:
        self._session = session

    def render(self) -> None:
        username = self._session.username
        if username:
            print(f"\n=== Chess === (logged in as {username}, ELO: {self._session.elo})")
        else:
            print("\n=== Chess ===")
        print("1) Login")
        print("2) Register")
        print("3) Play")
        print("4) Room")
        print("5) Quit")

    def get_choice(self) -> str:
        return input("Choice: ").strip()
