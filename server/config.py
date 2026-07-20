"""
config.py — all game constants in one place.

Reason for a separate file: changing one value (e.g. piece speed) does not require
touching any logic. Every layer imports from here and defines no constants of its own.
"""
from dataclasses import dataclass, field

# ── Board ──────────────────────────────────────────────────────────────
EMPTY_CELL       = "."        # empty cell representation in the grid
BOARD_SECTION    = "Board:"   # header for the board section in input
COMMANDS_SECTION = "Commands:" # header for the commands section in input

# ── Colors ─────────────────────────────────────────────────────────────
WHITE = 'w'
BLACK = 'b'

# ── Piece type codes ───────────────────────────────────────────────────
KING   = 'K'
QUEEN  = 'Q'
ROOK   = 'R'
BISHOP = 'B'
KNIGHT = 'N'
PAWN   = 'P'

# ── Pawn direction ─────────────────────────────────────────────────────
# white moves toward smaller row indices (up), black toward larger (down)
WHITE_DIRECTION = -1
BLACK_DIRECTION =  1

# ── UI ─────────────────────────────────────────────────────────────────
# click at pixel (x, y) maps to grid via: col = x // 100, row = y // 100
PIXEL_TO_GRID_DIVISOR = 100

# ── Command names ──────────────────────────────────────────────────────
CLICK_COMMAND = "click"
JUMP_COMMAND  = "jump"
WAIT_COMMAND  = "wait"
PRINT_COMMAND = "print"

# ── Expected argument counts per command ──────────────────────────────
CLICK_ARGS = 3   # click x y
JUMP_ARGS  = 3   # jump x y
WAIT_ARGS  = 2   # wait ms
PRINT_ARGS = 1   # print board


@dataclass
class GameConfig:
    """
    All values that affect game behaviour — injected into GameEngine.

    This separation allows:
    - tests with different values (e.g. high speed) without changing global constants
    - future flexibility to pass different settings per game
    """
    move_duration_ms: dict[str, int] = field(default_factory=lambda: {
        KING:   1000,
        QUEEN:  1000,
        ROOK:   1000,
        BISHOP: 1000,
        KNIGHT: 1500,
        PAWN:    500,
    })
    piece_score: dict[str, int] = field(default_factory=lambda: {
        KING:   0,
        QUEEN:  9,
        ROOK:   5,
        BISHOP: 3,
        KNIGHT: 3,
        PAWN:   1,
    })
    jump_duration_ms: int = 1000
    cooldown_ms: int = 3000


# Default config — used in GameRunner and tests that don't specify an explicit config
DEFAULT_CONFIG = GameConfig()
