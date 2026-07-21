"""
Phase 3 unit tests: domain/elo.py pure functions and RatingService.

Known ELO scenarios verified against hand-computed expected values.
K=32, standard formula.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.domain.elo import expected_score, calculate_elo, calculate_both
from server.domain.enums import GameResult
from server.services.rating_service import RatingService
from server.config_loader import load_settings


K = 32


# ── expected_score ─────────────────────────────────────────────────────────────

class TestExpectedScore:
    def test_equal_ratings_returns_half(self):
        assert abs(expected_score(1200, 1200) - 0.5) < 0.0001

    def test_higher_rated_has_higher_expectation(self):
        assert expected_score(1400, 1200) > 0.5

    def test_lower_rated_has_lower_expectation(self):
        assert expected_score(1000, 1200) < 0.5

    def test_400_point_advantage(self):
        # 400-point difference → expected ≈ 0.909
        exp = expected_score(1600, 1200)
        assert abs(exp - 0.909) < 0.001

    def test_symmetry(self):
        a, b = 1300, 1100
        assert abs(expected_score(a, b) + expected_score(b, a) - 1.0) < 0.0001


# ── calculate_elo ─────────────────────────────────────────────────────────────

class TestCalculateElo:
    def test_win_increases_elo_for_equal_players(self):
        new = calculate_elo(1200, 1200, 1.0, K)
        assert new == 1216  # 1200 + 32 * (1.0 - 0.5)

    def test_loss_decreases_elo_for_equal_players(self):
        new = calculate_elo(1200, 1200, 0.0, K)
        assert new == 1184  # 1200 + 32 * (0.0 - 0.5)

    def test_draw_no_change_for_equal_players(self):
        new = calculate_elo(1200, 1200, 0.5, K)
        assert new == 1200  # 1200 + 32 * (0.5 - 0.5)

    def test_underdog_wins_gains_more(self):
        # Lower-rated beats higher-rated → larger gain
        gain_underdog = calculate_elo(1000, 1400, 1.0, K) - 1000
        gain_favorite = calculate_elo(1400, 1000, 1.0, K) - 1400
        assert gain_underdog > gain_favorite

    def test_favorite_loses_more_elo(self):
        loss_favorite = 1400 - calculate_elo(1400, 1000, 0.0, K)
        loss_underdog = 1000 - calculate_elo(1000, 1400, 0.0, K)
        assert loss_favorite > loss_underdog

    def test_known_scenario_white_1200_black_1200_white_wins(self):
        # Both at 1200, white wins → white = 1216, black = 1184
        nw = calculate_elo(1200, 1200, 1.0, K)
        nb = calculate_elo(1200, 1200, 0.0, K)
        assert nw == 1216
        assert nb == 1184


# ── calculate_both ────────────────────────────────────────────────────────────

class TestCalculateBoth:
    def test_white_wins_equal(self):
        nw, nb = calculate_both(1200, 1200, GameResult.WHITE_WINS, K)
        assert nw == 1216
        assert nb == 1184

    def test_black_wins_equal(self):
        nw, nb = calculate_both(1200, 1200, GameResult.BLACK_WINS, K)
        assert nw == 1184
        assert nb == 1216

    def test_draw_equal(self):
        nw, nb = calculate_both(1200, 1200, GameResult.DRAW, K)
        assert nw == 1200
        assert nb == 1200

    def test_aborted_no_change(self):
        nw, nb = calculate_both(1200, 1400, GameResult.ABORTED, K)
        assert nw == 1200
        assert nb == 1400

    def test_unequal_draw_transfers_from_higher(self):
        # 1400 vs 1000 draw: ELO flows from 1400 to 1000
        nw, nb = calculate_both(1400, 1000, GameResult.DRAW, K)
        assert nw < 1400
        assert nb > 1000

    def test_total_elo_conserved_on_win(self):
        """Sum of ELOs should be roughly conserved (rounding may cause ±1)."""
        nw, nb = calculate_both(1200, 1200, GameResult.WHITE_WINS, K)
        assert abs((nw + nb) - (1200 + 1200)) <= 1

    def test_known_scenario_1200_vs_1400_white_wins(self):
        # Expected scores: white=1/(1+10^(200/400)) ≈ 0.240, black ≈ 0.760
        # white new = 1200 + 32*(1-0.240) = 1200 + 24.32 ≈ 1224
        # black new = 1400 + 32*(0-0.760) = 1400 - 24.32 ≈ 1376
        nw, nb = calculate_both(1200, 1400, GameResult.WHITE_WINS, K)
        assert nw == 1224
        assert nb == 1376


# ── RatingService ─────────────────────────────────────────────────────────────

class TestRatingService:
    def _svc(self) -> RatingService:
        return RatingService(load_settings())

    def test_delegates_to_elo(self):
        svc = self._svc()
        nw, nb = svc.update_ratings(1200, 1200, GameResult.WHITE_WINS)
        assert nw == 1216
        assert nb == 1184

    def test_does_not_mutate_inputs(self):
        svc = self._svc()
        white_before, black_before = 1300, 1100
        svc.update_ratings(white_before, black_before, GameResult.DRAW)
        assert white_before == 1300
        assert black_before == 1100

    def test_aborted_returns_unchanged(self):
        svc = self._svc()
        nw, nb = svc.update_ratings(1300, 1100, GameResult.ABORTED)
        assert nw == 1300
        assert nb == 1100
