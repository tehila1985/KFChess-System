import sys
from engine.game_engine import GameEngine
from engine.rules.rule_engine import RuleEngine
from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.models.board import Board
from engine.config import BOARD_SECTION, COMMANDS_SECTION, PIXEL_TO_GRID_DIVISOR, EMPTY_CELL, WHITE, BLACK
from ui.controller import Controller
from ui.text_renderer import TextRenderer
from ui.board_mapper import BoardMapper

_VALID_COLORS = {WHITE, BLACK}
_VALID_TYPES  = {'K', 'Q', 'R', 'B', 'N', 'P'}


def _validate_board(board_lines):
    if not board_lines:
        return "ERROR NO_BOARD"
    width = len(board_lines[0].split())
    for row in board_lines:
        tokens = row.split()
        if len(tokens) != width:
            return "ERROR ROW_WIDTH_MISMATCH"
        for token in tokens:
            if token == EMPTY_CELL:
                continue
            if len(token) != 2 or token[0] not in _VALID_COLORS or token[1] not in _VALID_TYPES:
                return "ERROR UNKNOWN_TOKEN"
    return None


class GameRunner:
    def __init__(self):
        self.renderer = TextRenderer()

    def run(self, input_stream):
        lines = input_stream.readlines()
        i = 0
        board_lines = []
        commands = []

        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if line == BOARD_SECTION:
                while i < len(lines) and lines[i].strip() != COMMANDS_SECTION:
                    board_lines.append(lines[i].strip())
                    i += 1
            elif line == COMMANDS_SECTION:
                commands = [l.strip() for l in lines[i:] if l.strip()]
                break

        error = _validate_board(board_lines)
        if error:
            print(error)
            return

        board = Board(board_lines)
        arbiter = RealTimeArbiter(board)
        rule_engine = RuleEngine()
        engine = GameEngine(board=board, rule_engine=rule_engine, arbiter=arbiter)
        mapper = BoardMapper(
            cell_size=PIXEL_TO_GRID_DIVISOR,
            rows=board.rows,
            cols=board.cols
        )
        controller = Controller(engine, mapper)

        for line in commands:
            parts = line.split()
            if not parts:
                continue

            if parts[0] == "click" and len(parts) == 3:
                controller.on_click(int(parts[1]), int(parts[2]))

            elif parts[0] == "jump" and len(parts) == 3:
                engine.request_jump(int(parts[1]), int(parts[2]))

            elif parts[0] == "wait" and len(parts) == 2:
                engine.tick(int(parts[1]))

            elif parts[0] == "print":
                snapshot = engine.get_snapshot()
                print(self.renderer.render_board_only(snapshot))
