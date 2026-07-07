import re

def validate_board(board_lines):
    if not board_lines: return False
    width = len(board_lines[0].split())
    for row in board_lines:
        tokens = row.split()
        if len(tokens) != width:
            return "ERROR ROW_WIDTH_MISMATCH"
        for token in tokens:
            if token != "." and not re.match(r'^[wb][KQRBNP]$', token):
                return "ERROR UNKNOWN_TOKEN"
    return True

def print_board(board):
    for row in board:
        print(" ".join(row))