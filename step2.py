from step1 import validate_board, print_board, Board
from pieces import PieceRegistry


class Action:
    """מייצג פעולת תנועה עם תזמון"""
    def __init__(self, start, end, start_time, duration):
        self.start = start
        self.end = end
        self.start_time = start_time
        self.duration = duration

    @property
    def end_time(self):
        return self.start_time + self.duration


class GameEngine:
    COOLDOWN_MS = 500  # זמן מנוחה לאחר הגעה ליעד

    def __init__(self, board):
        self.board = board
        self.selected = None
        self.current_time = 0
        self.action_queue = []          # פעולות ממתינות
        self.cooldowns = {}             # (r,c) -> זמן שבו הכלי פנוי שוב
        self.scores = {'w': 0, 'b': 0}

    def _piece_type(self, r, c):
        token = self.board.get(r, c)
        if token == ".":
            return None
        return PieceRegistry.get(token[1])

    def _is_on_cooldown(self, r, c):
        return self.cooldowns.get((r, c), 0) > self.current_time

    def _travel_time(self, start, end, piece_type):
        dist = max(abs(start[0] - end[0]), abs(start[1] - end[1]))
        return dist * piece_type.speed_ms

    def _flush_actions(self):
        """מבצע את כל הפעולות שהגיע זמנן"""
        done = [a for a in self.action_queue if a.end_time <= self.current_time]
        for action in done:
            self.action_queue.remove(action)
            sr, sc = action.start
            tr, tc = action.end
            # בדיקה שהכלי עדיין שם (לא נאכל בינתיים)
            token = self.board.get(sr, sc)
            if token == ".":
                continue
            captured = self.board.move_piece(action.start, action.end)
            if captured != ".":
                color = captured[0]
                pt = PieceRegistry.get(captured[1])
                if pt:
                    winner = 'w' if color == 'b' else 'b'
                    self.scores[winner] += pt.score
            self.cooldowns[(tr, tc)] = action.end_time + self.COOLDOWN_MS

    def click(self, x, y):
        col, row = x // 100, y // 100
        if not self.board.in_bounds(row, col):
            return

        self._flush_actions()
        target = self.board.get(row, col)

        if self.selected:
            sr, sc = self.selected
            p_token = self.board.get(sr, sc)
            pt = self._piece_type(sr, sc)

            if target != "." and target[0] == p_token[0]:
                # בחירה מחדש של כלי אחר מאותו צד
                self.selected = (row, col)
                return

            if pt and pt.is_legal_move((sr, sc), (row, col)) \
                    and not self.board.is_path_blocked((sr, sc), (row, col), pt.is_jumper()) \
                    and not self._is_on_cooldown(sr, sc):
                duration = self._travel_time((sr, sc), (row, col), pt)
                self.action_queue.append(Action((sr, sc), (row, col), self.current_time, duration))
                self.selected = None
            else:
                self.selected = None
        elif target != ".":
            self.selected = (row, col)

    def wait(self, ms):
        self.current_time += ms
        self._flush_actions()

    def is_game_over(self):
        """ניצחון = אכילת מלך היריב"""
        return self.scores['w'] == float('inf') or self.scores['b'] == float('inf')


class GameRunner:
    def run(self, input_data):
        lines = input_data.strip().splitlines()
        board_lines, commands = [], []
        mode = "NONE"
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line == "Board:":
                mode = "BOARD"
            elif line == "Commands:":
                mode = "COMMANDS"
            elif mode == "BOARD":
                board_lines.append(line)
            elif mode == "COMMANDS":
                commands.append(line)

        val = validate_board(board_lines)
        if val is not True:
            print(val)
            return

        board = Board(board_lines)
        engine = GameEngine(board)

        for cmd in commands:
            parts = cmd.split()
            if not parts:
                continue
            if parts[0] == "click":
                engine.click(int(parts[1]), int(parts[2]))
            elif parts[0] == "wait":
                engine.wait(int(parts[1]))
            elif parts[0] == "print":
                print_board(engine.board.grid)
