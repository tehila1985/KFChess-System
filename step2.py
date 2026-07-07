from step1 import validate_board, print_board
from pieces import King, Rook, Bishop, Queen, Knight

# מילון המחלקות שקובעות את חוקי התנועה של כל כלי
PIECE_MAP = {'K': King(), 'R': Rook(), 'B': Bishop(), 'Q': Queen(), 'N': Knight()}

class GameRunner:
    def run(self, input_data):
        lines = input_data.strip().splitlines()
        board_lines, commands = [], []
        mode = "NONE"
        for line in lines:
            line = line.strip()
            if not line: continue
            if line == "Board:": mode = "BOARD"
            elif line == "Commands:": mode = "COMMANDS"
            elif mode == "BOARD": board_lines.append(line)
            elif mode == "COMMANDS": commands.append(line)

        # 1. בדיקת תקינות הלוח (מ-step1)
        val = validate_board(board_lines)
        if val != True:
            print(val); return

        # 2. הרצת המנוע
        game = KFChessEngine(board_lines)
        for cmd in commands:
            parts = cmd.split()
            if parts[0] == "click": game.click(int(parts[1]), int(parts[2]))
            elif parts[0] == "wait": game.wait(int(parts[1]))
            elif parts[0] == "print": print_board(game.board)

class KFChessEngine:
    def __init__(self, board_lines):
        self.board = [line.split() for line in board_lines]
        self.selected = None
        self.move_queue = []

    def is_path_blocked(self, start, end):
        sr, sc = start
        tr, tc = end
        # פרש (Knight) תמיד יכול לקפוץ
        if isinstance(PIECE_MAP.get(self.board[sr][sc][1]), Knight):
            return False
            
        dr = 0 if sr == tr else (1 if tr > sr else -1)
        dc = 0 if sc == tc else (1 if tc > sc else -1)
        
        r, c = sr + dr, sc + dc
        # בודקים אם יש כלי בדרך
        while (r, c) != (tr, tc):
            if not (0 <= r < len(self.board) and 0 <= c < len(self.board[0])): return True
            if self.board[r][c] != ".": return True
            r += dr; c += dc
        return False

    def click(self, x, y):
        col, row = x // 100, y // 100
        if not (0 <= row < len(self.board) and 0 <= col < len(self.board[0])): return
        target = self.board[row][col]
        
        if self.selected:
            sr, sc = self.selected
            p_token = self.board[sr][sc]
            logic = PIECE_MAP.get(p_token[1])
            
            # אם בחרנו כלי שלנו - מחליפים בחירה
            if target != "." and target[0] == p_token[0]:
                self.selected = (row, col)
            # אם המהלך חוקי גיאומטרית ואין חסימות - מוסיפים לתור
            elif logic and logic.is_legal((sr, sc), (row, col)) and not self.is_path_blocked((sr, sc), (row, col)):
                self.move_queue.append(((sr, sc), (row, col)))
                self.selected = None
            else: self.selected = None
        elif target != ".": 
            # בחירת כלי (רק אם הוא שייך אלינו)
            self.selected = (row, col)

    def wait(self, ms):
        # המהלך מתבצע כאן: דורס את משבצת היעד (אכילה)
        while self.move_queue:
            (sr, sc), (tr, tc) = self.move_queue.pop(0)
            self.board[tr][tc] = self.board[sr][sc]
            self.board[sr][sc] = "."