from server.game_engine import GameEngine
from server.rules.rule_engine import RuleEngine
from server.arbiter.real_time_arbiter import RealTimeArbiter
from server.models.board import Board
from server.config import BOARD_SECTION, COMMANDS_SECTION, PIXEL_TO_GRID_DIVISOR, EMPTY_CELL, WHITE, BLACK, DEFAULT_CONFIG
from ui.interaction.controller import Controller
from ui.presentation.text_renderer import TextRenderer
from ui.interaction.board_mapper import BoardMapper

_VALID_COLORS = {WHITE, BLACK}
_VALID_TYPES  = {'K', 'Q', 'R', 'B', 'N', 'P'}


def _validate_board(board_lines):
    """
    Validates the board before creating the game.

    Checks:
    - Board is not empty
    - All rows have the same width (ROW_WIDTH_MISMATCH)
    - Each token is '.' or a valid color+type combination (UNKNOWN_TOKEN)

    Returns an error string or None if everything is valid.
    """
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
    """
    Logical entry point — connects textual input to the game engine.

    Responsibilities:
    1. Parse input into Board and Commands sections
    2. Validate the board
    3. Build all layers (Board → RuleEngine → Arbiter → GameEngine → Controller)
    4. Execute commands in order

    Separated from GameEngine because Runner understands input/output format,
    while GameEngine knows nothing about text or stdin.
    """

    def __init__(self):
        self.renderer = TextRenderer()

    def run(self, input_stream):
        lines = input_stream.readlines()
        i = 0
        board_lines = []
        commands    = []

        # Parsing: splits input into board section and commands section
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

        # Build layers — order matters: Board first, then everything that depends on it
        board       = Board(board_lines)
        config      = DEFAULT_CONFIG
        arbiter     = RealTimeArbiter(board, config)
        rule_engine = RuleEngine()
        engine      = GameEngine(board=board, rule_engine=rule_engine, arbiter=arbiter, config=config)
        mapper     = BoardMapper(cell_size=PIXEL_TO_GRID_DIVISOR, rows=board.rows, cols=board.cols)
        controller = Controller(engine, mapper)

        # Execute commands in order
        for line in commands:
            parts = line.split()
            if not parts:
                continue

            if parts[0] == "click" and len(parts) == 3:
                # click x y — select/move via Controller
                controller.on_click(int(parts[1]), int(parts[2]))

            elif parts[0] == "jump" and len(parts) == 3:
                # jump x y — convert pixel to Position via BoardMapper, then jump
                pos = mapper.to_position(int(parts[1]), int(parts[2]))
                if pos is not None:
                    engine.request_jump(pos)

            elif parts[0] == "wait" and len(parts) == 2:
                # wait ms — advances the simulation clock
                engine.tick(int(parts[1]))

            elif parts[0] == "print":
                # print board — prints the current board state
                snapshot = engine.get_snapshot()
                print(self.renderer.render_board_only(snapshot))
