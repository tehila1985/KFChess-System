"""
rating_service.py — wraps domain/elo.py; no I/O.

SRP: ELO calculation only. Persistence is the caller's job via UserRepository.
"""
from __future__ import annotations

from server.domain.elo import calculate_both
from server.domain.enums import GameResult
from server.config_loader import Settings


class RatingService:
    """
    Pure computation wrapper around elo.py.

    Takes settings as constructor parameter for k_factor (DI).
    Does not touch the database; returns new ELO values to the caller.
    """

    def __init__(self, settings: Settings) -> None:
        self._k_factor = settings.rating.k_factor

    def update_ratings(
        self, white_elo: int, black_elo: int, result: GameResult
    ) -> tuple[int, int]:
        """
        Calculate new ELOs for both players.

        Args:
            white_elo: White player's current ELO.
            black_elo: Black player's current ELO.
            result: GameResult (WHITE_WINS, BLACK_WINS, DRAW, ABORTED).

        Returns:
            (new_white_elo, new_black_elo) — integers.
        """
        return calculate_both(white_elo, black_elo, result, self._k_factor)
