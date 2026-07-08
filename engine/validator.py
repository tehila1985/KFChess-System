import re
from engine.config import EMPTY_CELL, WHITE, BLACK, KING, QUEEN, ROOK, BISHOP, KNIGHT, PAWN

VALID_TOKEN = re.compile(r'^[wb][KQRBNP]$')


def validate_board(board_lines):
    if not board_lines:
        return False
    width = len(board_lines[0].split())
    for row in board_lines:
        tokens = row.split()
        if len(tokens) != width:
            return "ERROR ROW_WIDTH_MISMATCH"
        for token in tokens:
            if token != EMPTY_CELL and not VALID_TOKEN.match(token):
                return "ERROR UNKNOWN_TOKEN"
    return True
