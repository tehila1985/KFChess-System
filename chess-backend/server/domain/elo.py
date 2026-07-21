"""
elo.py — pure ELO calculation functions.

No I/O, no state, no side effects. Heavily unit-tested.

Formula:
    expected_score = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    new_elo = old_elo + K * (actual_score - expected_score)

actual_score: 1.0 = win, 0.5 = draw, 0.0 = loss
"""
from __future__ import annotations

from server.domain.enums import GameResult


def expected_score(player_elo: int, opponent_elo: int) -> float:
    """
    Calculate the expected score for a player against an opponent.

    Returns a float in [0, 1]: probability of winning.
    """
    return 1.0 / (1.0 + 10.0 ** ((opponent_elo - player_elo) / 400.0))


def calculate_elo(
    player_elo: int,
    opponent_elo: int,
    actual_score: float,
    k_factor: int,
) -> int:
    """
    Calculate new ELO for a player after a game.

    Args:
        player_elo: Player's current ELO.
        opponent_elo: Opponent's current ELO.
        actual_score: 1.0 = win, 0.5 = draw, 0.0 = loss.
        k_factor: K-factor (e.g. 32).

    Returns:
        New ELO as an integer (rounded).
    """
    exp = expected_score(player_elo, opponent_elo)
    new_elo = player_elo + k_factor * (actual_score - exp)
    return round(new_elo)


def calculate_both(
    white_elo: int,
    black_elo: int,
    result: GameResult,
    k_factor: int,
) -> tuple[int, int]:
    """
    Calculate new ELOs for both players after a game.

    Args:
        white_elo: White player's current ELO.
        black_elo: Black player's current ELO.
        result: GameResult enum value.
        k_factor: K-factor from config.

    Returns:
        (new_white_elo, new_black_elo) as integers.
    """
    if result == GameResult.WHITE_WINS:
        white_score, black_score = 1.0, 0.0
    elif result == GameResult.BLACK_WINS:
        white_score, black_score = 0.0, 1.0
    elif result == GameResult.DRAW:
        white_score, black_score = 0.5, 0.5
    else:
        # Aborted — no rating change
        return white_elo, black_elo

    new_white = calculate_elo(white_elo, black_elo, white_score, k_factor)
    new_black = calculate_elo(black_elo, white_elo, black_score, k_factor)
    return new_white, new_black
