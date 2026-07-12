"""
config.py — כל ה-constants של המשחק במקום אחד.

הסיבה לקובץ נפרד: שינוי ערך אחד (כמו מהירות כלי) לא מצריך
לגעת בלוגיקה. כל שכבה מייבאת מכאן ולא מגדירה קבועים בעצמה.
"""
from dataclasses import dataclass, field

# ── Board ──────────────────────────────────────────────────────────────
EMPTY_CELL       = "."        # ייצוג תא ריק בגריד
BOARD_SECTION    = "Board:"   # כותרת חלק הלוח בקלט
COMMANDS_SECTION = "Commands:" # כותרת חלק הפקודות בקלט

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
# לבן זז לשורות קטנות יותר (מעלה), שחור לשורות גדולות יותר (מטה)
WHITE_DIRECTION = -1
BLACK_DIRECTION =  1

# ── UI ─────────────────────────────────────────────────────────────────
# קליק בפיקסל (x, y) ממופה לגריד לפי: col = x // 100, row = y // 100
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
    כל הערכים שמשפיעים על התנהגות המשחק — מוזרקים ל-GameEngine.

    הפרדה זו מאפשרת:
    - טסטים עם ערכים שונים (למשל מהירות גבוהה) בלי לשנות קבועים גלובליים
    - גמישות עתידית להעביר הגדרות שונות per-game
    """
    move_duration_ms: dict = field(default_factory=lambda: {
        KING:   1000,
        QUEEN:  1000,
        ROOK:   1000,
        BISHOP: 1000,
        KNIGHT: 1500,
        PAWN:    500,
    })
    piece_score: dict = field(default_factory=lambda: {
        KING:   float('inf'),
        QUEEN:  9,
        ROOK:   5,
        BISHOP: 3,
        KNIGHT: 3,
        PAWN:   1,
    })
    jump_duration_ms: int = 1000


# ברירת המחדל — בשימוש ב-GameRunner ובטסטים שלא מציינים config מפורש
DEFAULT_CONFIG = GameConfig()
