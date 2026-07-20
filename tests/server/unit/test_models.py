import pytest
from server.models.board import Board
from server.models.piece import Piece
from server.models.position import Position


@pytest.fixture
def board():
    return Board(["wR . .", ". wK .", ". . bP"])


# ── in_bounds ──────────────────────────────────────────────────────────

def test_in_bounds_valid(board):
    """Verify in bounds valid."""
    assert board.in_bounds(Position(0, 0))
    assert board.in_bounds(Position(2, 2))

def test_in_bounds_negative(board):
    """Verify in bounds negative."""
    assert not board.in_bounds(Position(-1, 0))
    assert not board.in_bounds(Position(0, -1))

def test_in_bounds_overflow(board):
    """Verify in bounds overflow."""
    assert not board.in_bounds(Position(3, 0))
    assert not board.in_bounds(Position(0, 3))


# ── get_piece ──────────────────────────────────────────────────────────

def test_get_piece_returns_piece(board):
    """Verify get piece returns piece."""
    piece = board.get_piece(Position(0, 0))
    assert piece == Piece(color="w", type_code="R")

def test_get_piece_empty_returns_none(board):
    """Verify get piece empty returns none."""
    assert board.get_piece(Position(0, 1)) is None

def test_get_piece_black(board):
    """Verify get piece black."""
    piece = board.get_piece(Position(2, 2))
    assert piece == Piece(color="b", type_code="P")


# ── set_piece ──────────────────────────────────────────────────────────

def test_set_piece_places_piece(board):
    """Verify set piece places piece."""
    board.set_piece(Position(0, 1), Piece("b", "Q"))
    assert board.get_piece(Position(0, 1)) == Piece("b", "Q")

def test_set_piece_none_clears_cell(board):
    """Verify set piece none clears cell."""
    board.set_piece(Position(0, 0), None)
    assert board.is_empty(Position(0, 0))

def test_set_piece_overwrites_existing(board):
    """Verify set piece overwrites existing."""
    board.set_piece(Position(1, 1), Piece("b", "K"))
    assert board.get_piece(Position(1, 1)) == Piece("b", "K")


# ── is_empty ───────────────────────────────────────────────────────────

def test_is_empty_on_empty_cell(board):
    """Verify is empty on empty cell."""
    assert board.is_empty(Position(0, 1))

def test_is_empty_on_occupied_cell(board):
    """Verify is empty on occupied cell."""
    assert not board.is_empty(Position(0, 0))

def test_is_empty_after_clear(board):
    """Verify is empty after clear."""
    board.set_piece(Position(0, 0), None)
    assert board.is_empty(Position(0, 0))
