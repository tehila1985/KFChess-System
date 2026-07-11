"""
config.py — כל ה-constants של המשחק במקום אחד.

הסיבה לקובץ נפרד: שינוי ערך אחד (כמו מהירות כלי) לא מצריך
לגעת בלוגיקה. כל שכבה מייבאת מכאן ולא מגדירה קבועים בעצמה.
"""

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

# ── Move durations (ms per cell) ───────────────────────────────────────
# כל כלי לוקח זמן קבוע לכל תא שהוא עובר.
# פרש (N) איטי יותר כי הוא קופץ ולא הולך בנתיב ישר.
MOVE_DURATION_MS = {
    KING:   1000,
    QUEEN:  1000,
    ROOK:   1000,
    BISHOP: 1000,
    KNIGHT: 1500,
    PAWN:    500,
}

# ── Piece score values ─────────────────────────────────────────────────
# ערך כל כלי לצורך ניקוד. מלך = אינסוף כי לכידתו מסיימת משחק.
PIECE_SCORE = {
    KING:   float('inf'),
    QUEEN:  9,
    ROOK:   5,
    BISHOP: 3,
    KNIGHT: 3,
    PAWN:   1,
}

# ── Jump ───────────────────────────────────────────────────────────────
# קפיצה היא פעולה מיוחדת: הכלי "עף" מעל הלוח ונוחת באותה משבצת.
# בזמן הקפיצה הוא יכול ללכוד כלי אויב שמגיע לאותה משבצת.
JUMP_DURATION_MS = 1000

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
