from __future__ import annotations

from server.arbiter.real_time_arbiter import RealTimeArbiter
from server.config import BLACK, DEFAULT_CONFIG, WHITE
from server.game_engine import GameEngine, RequestMoveResult
from server.models.board import Board
from server.models.piece import Piece
from server.models.position import Position
from server.rules.rule_engine import RuleEngine


def pos(row: int, col: int) -> Position:
    return Position(row, col)


def make_engine(board_lines: list[str], config=DEFAULT_CONFIG) -> GameEngine:
    board = Board(board_lines)
    arbiter = RealTimeArbiter(board, config)
    return GameEngine(board, RuleEngine(), arbiter, config)


def test_piece_score_table_matches_expected_values() -> None:
    """Verify the configured material values match the required scoring table."""
    assert DEFAULT_CONFIG.piece_score["P"] == 1
    assert DEFAULT_CONFIG.piece_score["N"] == 3
    assert DEFAULT_CONFIG.piece_score["B"] == 3
    assert DEFAULT_CONFIG.piece_score["R"] == 5
    assert DEFAULT_CONFIG.piece_score["Q"] == 9
    assert DEFAULT_CONFIG.piece_score["K"] == 0


def test_capture_awards_target_piece_value_not_flat_point() -> None:
    """Verify that capturing a rook awards five points instead of a flat one-point reward."""
    engine = make_engine(["wR . bR"])
    assert engine.request_move(pos(0, 0), pos(0, 2)) == RequestMoveResult.ACCEPTED

    engine.tick(2000)

    snapshot = engine.get_snapshot()
    assert dict(snapshot.scores)[WHITE] == 5
    assert dict(snapshot.scores)[BLACK] == 0


def test_capturing_piece_keeps_its_original_identity() -> None:
    """Verify that the attacking piece remains the same token after a capture resolves."""
    engine = make_engine(["wR . bR"])
    attacker_before = engine.get_piece_at(pos(0, 0))

    assert engine.request_move(pos(0, 0), pos(0, 2)) == RequestMoveResult.ACCEPTED
    engine.tick(2000)

    attacker_after = engine.get_piece_at(pos(0, 2))
    assert attacker_before == Piece("w", "R")
    assert attacker_after == Piece("w", "R")
    assert engine.get_snapshot().grid[0][2] == "wR"


def test_king_capture_routes_through_dedicated_handler() -> None:
    """Verify that king capture ends the game through the king-capture path and not via material scoring."""
    engine = make_engine(["wR . bK"])
    assert engine.request_move(pos(0, 0), pos(0, 2)) == RequestMoveResult.ACCEPTED

    engine.tick(2000)

    snapshot = engine.get_snapshot()
    assert snapshot.game_over is True
    assert snapshot.winner == WHITE
    assert dict(snapshot.scores)[WHITE] == 0
