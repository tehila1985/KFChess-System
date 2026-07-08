import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.parser import parse_input
from engine.validator import validate_board
from engine.board import Board
from engine.game_logic import GameEngine


def run():
    input_data = sys.stdin.read()
    board_lines, commands = parse_input(input_data)

    val = validate_board(board_lines)
    if val is not True:
        print(val)
        return

    board = Board(board_lines)
    engine = GameEngine(board)

    for cmd in commands:
        parts = cmd.split()
        if not parts:
            continue
        if parts[0] == "click":
            engine.click(int(parts[1]), int(parts[2]))
        elif parts[0] == "wait":
            engine.wait(int(parts[1]))
        elif parts[0] == "print":
            engine.board.display()
