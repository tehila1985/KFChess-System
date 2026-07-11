"""
Game Configuration - מקום מרכזי לכל ה-constants
"""

# ========== Board Constants ==========
EMPTY_CELL = "."
BOARD_SECTION = "Board:"
COMMANDS_SECTION = "Commands:"

# ========== Colors ==========
WHITE = 'w'
BLACK = 'b'

# ========== Piece Codes ==========
KING = 'K'
QUEEN = 'Q'
ROOK = 'R'
BISHOP = 'B'
KNIGHT = 'N'
PAWN = 'P'

# ========== Direction Constants ==========
WHITE_DIRECTION = -1  # לבן זז "למעלה" (rows קטנות)
BLACK_DIRECTION = 1   # שחור זז "למטה" (rows גדולות)

# ========== Move Duration (milliseconds) ==========
MOVE_DURATION_MS = {
    KING:   1000,
    QUEEN:  1000,
    ROOK:   1000,
    BISHOP: 1000,
    KNIGHT: 1500,
    PAWN:   500,
}

# ========== Piece Score Values ==========
PIECE_SCORE = {
    KING: float('inf'),
    QUEEN: 9,
    ROOK: 5,
    BISHOP: 3,
    KNIGHT: 3,
    PAWN: 1,
}

# ========== Action Durations ==========
JUMP_DURATION_MS = 1000

# ========== UI Constants ==========
PIXEL_TO_GRID_DIVISOR = 100  # קליק בפיקסל (x, y) → grid[y//100, x//100]

# ========== Command Names ==========
CLICK_COMMAND = "click"
JUMP_COMMAND = "jump"
WAIT_COMMAND = "wait"
PRINT_COMMAND = "print"

# ========== Command Argument Counts ==========
CLICK_ARGS = 3      # click x y
JUMP_ARGS = 3       # jump x y
WAIT_ARGS = 2       # wait ms
PRINT_ARGS = 1      # print
