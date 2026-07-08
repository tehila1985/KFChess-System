import sys
from utils.parser import parse_input
from engine.validator import validate_board
from engine.board import Board
from engine.game_logic import GameEngine
from engine.config import CLICK_COMMAND, JUMP_COMMAND, WAIT_COMMAND, PRINT_COMMAND


def _parse_commands_from_input(commands):
    """
    עבור כל פקודה, פרוק אותה ל-(command_name, args).
    
    Responsibility אחד: פרוק את ה-raw strings לפקודות מובנות.
    """
    parsed = []
    for cmd in commands:
        parts = cmd.split()
        if parts:
            parsed.append((parts[0], parts[1:]))
    return parsed


def _execute_command(engine, command_name, args):
    """
    בצע פקודה יחידה על ה-engine.
    
    Responsibility אחד: dispatch לפקודה המתאימה.
    מניעת hard-coded command names ע״י שימוש בקבועים מ-config.
    """
    if command_name == CLICK_COMMAND and len(args) >= 2:
        engine.click(int(args[0]), int(args[1]))
    elif command_name == JUMP_COMMAND and len(args) >= 2:
        engine.jump(int(args[0]), int(args[1]))
    elif command_name == WAIT_COMMAND and len(args) >= 1:
        engine.wait(int(args[0]))
    elif command_name == PRINT_COMMAND:
        engine.display()


def run():
    """
    Main entry point: parse input → validate → create engine → execute commands.
    
    Responsibility אחד: Orchestrate the flow.
    """
    input_data = sys.stdin.read()
    board_lines, commands = parse_input(input_data)

    val = validate_board(board_lines)
    if val is not True:
        print(val)
        return

    board = Board(board_lines)
    engine = GameEngine(board)

    # Parse all commands
    parsed_commands = _parse_commands_from_input(commands)
    
    # Execute all commands
    for command_name, args in parsed_commands:
        _execute_command(engine, command_name, args)
