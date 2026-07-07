from step1 import validate_board, print_board
from pieces import King, Rook, Bishop, Queen, Knight

PIECE_MAP = {'K': King(), 'R': Rook(), 'B': Bishop(), 'Q': Queen(), 'N': Knight()}

class GameRunner: # <--- זה השם שה-main מחפש
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

        val = validate_board(board_lines)
        if val != True:
            print(val)
            return

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

    def click(self, x, y):
        col, row = x // 100, y // 100
        if not (0 <= row < len(self.board) and 0 <= col < len(self.board[0])): return
        target = self.board[row][col]
        
        if self.selected:
            sr, sc = self.selected
            piece_token = self.board[sr][sc]
            logic = PIECE_MAP.get(piece_token[1])
            
            if target != "." and target[0] == piece_token[0]: self.selected = (row, col)
            elif logic and logic.is_legal((sr, sc), (row, col)):
                self.move_queue.append(((sr, sc), (row, col)))
                self.selected = None
            else: self.selected = None
        elif target != ".": self.selected = (row, col)

    def wait(self, ms):
        while self.move_queue:
            (sr, sc), (tr, tc) = self.move_queue.pop(0)
            self.board[tr][tc] = self.board[sr][sc]
            self.board[sr][sc] = "."