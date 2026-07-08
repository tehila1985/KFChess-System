import re

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
            if token != "." and not VALID_TOKEN.match(token):
                return "ERROR UNKNOWN_TOKEN"
    return True


def print_board(board):
    for row in board:
        print(" ".join(row))


class Board:
    def __init__(self, board_lines):
        self.grid = [line.split() for line in board_lines]
        self.rows = len(self.grid)
        self.cols = len(self.grid[0]) if self.grid else 0

    def in_bounds(self, r, c):
        return 0 <= r < self.rows and 0 <= c < self.cols

    def get(self, r, c):
        return self.grid[r][c]

    def set(self, r, c, value):
        self.grid[r][c] = value

    def is_empty(self, r, c):
        return self.grid[r][c] == "."

    def is_path_blocked(self, start, end, is_jumper=False):
        if is_jumper:
            return False
        sr, sc = start
        tr, tc = end
        dr = 0 if sr == tr else (1 if tr > sr else -1)
        dc = 0 if sc == tc else (1 if tc > sc else -1)
        r, c = sr + dr, sc + dc
        while (r, c) != (tr, tc):
            if not self.in_bounds(r, c) or not self.is_empty(r, c):
                return True
            r += dr
            c += dc
        return False

    def move_piece(self, start, end):
        sr, sc = start
        tr, tc = end
        captured = self.grid[tr][tc]
        self.grid[tr][tc] = self.grid[sr][sc]
        self.grid[sr][sc] = "."
        return captured
