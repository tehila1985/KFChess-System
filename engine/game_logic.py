from engine.pieces import PieceRegistry


class Action:
    def __init__(self, start, end, start_time, duration):
        self.start = start
        self.end = end
        self.start_time = start_time
        self.duration = duration

    @property
    def end_time(self):
        return self.start_time + self.duration


class GameEngine:
    COOLDOWN_MS = 500

    def __init__(self, board):
        self.board = board
        self.selected = None
        self.current_time = 0
        self.action_queue = []
        self.cooldowns = {}
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
        done = [a for a in self.action_queue if a.end_time <= self.current_time]
        for action in done:
            self.action_queue.remove(action)
            sr, sc = action.start
            tr, tc = action.end
            if self.board.get(sr, sc) == ".":
                continue
            captured = self.board.move_piece(action.start, action.end)
            if captured != ".":
                pt = PieceRegistry.get(captured[1])
                if pt:
                    winner = 'w' if captured[0] == 'b' else 'b'
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
        return self.scores['w'] == float('inf') or self.scores['b'] == float('inf')
