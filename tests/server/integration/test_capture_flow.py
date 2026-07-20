from __future__ import annotations

from server.arbiter.real_time_arbiter import RealTimeArbiter
from server.config import WHITE
from server.game_engine import GameEngine, RequestMoveResult
from server.models.board import Board
from server.models.position import Position
from server.rules.rule_engine import RuleEngine
from ui.interaction.board_mapper import BoardMapper
from ui.interaction.controller import Controller


CELL = 100


def pos(row: int, col: int) -> Position:
    return Position(row, col)


def px(col: int, row: int) -> tuple[int, int]:
    return col * CELL + CELL // 2, row * CELL + CELL // 2


def build(board_lines: list[str]):
    board = Board(board_lines)
    arbiter = RealTimeArbiter(board)
    engine = GameEngine(board, RuleEngine(), arbiter)
    mapper = BoardMapper(cell_size=CELL, rows=len(board_lines), cols=len(board_lines[0].split()))
    controller = Controller(engine, mapper)
    return engine, controller


def test_capture_flow_preserves_attacker_and_scores_target_value() -> None:
    """Verify the full click-to-capture flow preserves the attacker token and awards the captured piece value."""
    engine, controller = build(["wR . bR"])

    assert controller.on_click(*px(0, 0)) is None
    assert controller.on_click(*px(2, 0)) == RequestMoveResult.ACCEPTED

    engine.tick(2000)

    snapshot = engine.get_snapshot()
    assert snapshot.grid[0][2] == "wR"
    assert dict(snapshot.scores)[WHITE] == 5


def test_king_capture_through_controller_ends_game() -> None:
    """Verify a king capture through the integration path ends the game and blocks later moves."""
    engine, controller = build(["wR . bK"])

    assert controller.on_click(*px(0, 0)) is None
    assert controller.on_click(*px(2, 0)) == RequestMoveResult.ACCEPTED

    engine.tick(2000)

    assert engine.get_snapshot().game_over is True

    assert controller.on_click(*px(2, 0)) is None
    assert controller.on_click(*px(1, 0)) == RequestMoveResult.GAME_OVER
