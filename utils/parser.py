import sys


def read_input():
    return sys.stdin.read().strip()


def parse_input(input_data):
    lines = input_data.strip().splitlines()
    board_lines, commands = [], []
    mode = "NONE"
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == "Board:":
            mode = "BOARD"
        elif line == "Commands:":
            mode = "COMMANDS"
        elif mode == "BOARD":
            board_lines.append(line)
        elif mode == "COMMANDS":
            commands.append(line)
    return board_lines, commands
