import sys
from engine.config import BOARD_SECTION, COMMANDS_SECTION


def read_input():
    return sys.stdin.read().strip()


def parse_input(input_data):
    """
    פרוק את input ל-board lines וcommands lines.
    
    עקרון DRY: משתמש בקבועים BOARD_SECTION וCOMMANDS_SECTION מ-config
    במקום hard-coded strings "Board:" ו"Commands:".
    """
    lines = input_data.strip().splitlines()
    board_lines, commands = [], []
    mode = "NONE"
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == BOARD_SECTION:
            mode = "BOARD"
        elif line == COMMANDS_SECTION:
            mode = "COMMANDS"
        elif mode == "BOARD":
            board_lines.append(line)
        elif mode == "COMMANDS":
            commands.append(line)
    return board_lines, commands
