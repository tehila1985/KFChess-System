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

    @property
    def is_jump(self):
        return self.start == self.end


class GameEngine:
    def __init__(self, board):
        self.board = board
        self.selected = None
        self.current_time = 0
        self.action_queue = []
        self.scores = {'w': 0, 'b': 0}

    def _piece_type(self, r, c):
        token = self.board.get(r, c)
        if token == ".":
            return None
        return PieceRegistry.get(token[1])

    def _is_moving(self, r, c):
        return any(a.start == (r, c) and not a.is_jump for a in self.action_queue)

    def _is_airborne(self, r, c):
        return any(a.is_jump and a.start == (r, c) for a in self.action_queue)

    def _is_destination_taken(self, tr, tc):
        # a destination is considered taken only if a NON-JUMP action is targeting it
        return any(a.end == (tr, tc) and not a.is_jump for a in self.action_queue)

    def _route_conflicts(self, start, end):
        """חוסם רק אם כלי אחר נע לאותה עמודה יעד מאותו כיוון (לא head-to-head)"""
        for a in self.action_queue:
            if a.end[1] == end[1] and a.start[1] != end[1]:
                # אותה עמודה יעד, ושניהם באים מאותו צד
                if (start[1] < end[1]) == (a.start[1] < a.end[1]):
                    return True
        return False

    def _travel_time(self, start, end, piece_type):
        return PieceRegistry.MOVE_DURATION_MS.get(piece_type.code, 1000)

    def _flush_actions(self):
        done = sorted(
            [a for a in self.action_queue if a.end_time <= self.current_time],
            key=lambda a: a.start_time
        )
        for action in done:
            if action in self.action_queue:
                self.action_queue.remove(action)

        # snapshot board before mutations so we can refer to original tokens
        snapshot = [row[:] for row in self.board.grid]

        losers = set()
        for i, action in enumerate(done):
            for j, other in enumerate(done):
                if i == j:
                    continue
                # head-to-head: other moves to action.start and action moves to other.start
                if other.end == action.start and other.start == action.end:
                    if other.start_time < action.start_time:
                        losers.add(i)
                    elif other.start_time == action.start_time and j < i:
                        losers.add(i)

        # First: resolve jumps capturing arriving movers (jumping piece stays in place)
        for i, action in enumerate(done):
            if i in losers or not action.is_jump:
                continue
            sr, sc = action.start
            if snapshot[sr][sc] == ".":
                continue
            # any arriving mover whose end == this jump's cell is captured (removed at its source)
            for j, other in enumerate(done):
                if j in losers or other is action or other.is_jump:
                    continue
                if other.end == action.start:
                    osr, osc = other.start
                    captured_token = snapshot[osr][osc]
                    if captured_token == ".":
                        continue
                    # remove arriving piece (it never lands)
                    self.board.set(osr, osc, ".")
                    # award score to jumper's side (captured token belongs to enemy)
                    pt = PieceRegistry.get(captured_token[1])
                    if pt:
                        winner = 'w' if captured_token[0] == 'b' else 'b'
                        self.scores[winner] += pt.score

        # Then: resolve normal moves (move_piece handles captures against non-airborne pieces)
        for i, action in enumerate(done):
            if i in losers or action.is_jump:
                continue
            sr, sc = action.start
            if self.board.get(sr, sc) == ".":
                continue
            captured = self.board.move_piece(action.start, action.end)
            if captured != ".":
                pt = PieceRegistry.get(captured[1])
                if pt:
                    winner = 'w' if captured[0] == 'b' else 'b'
                    self.scores[winner] += pt.score
            # promotion handling after move
            tr, tc = action.end
            token = self.board.get(tr, tc)
            if token and token[1] == 'P':
                color = token[0]
                promotion_row = 0 if color == 'w' else self.board.rows - 1
                if tr == promotion_row:
                    self.board.set(tr, tc, color + 'Q')

    def click(self, x, y):
        if self.is_game_over():
            return
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

            if pt and pt.is_legal_move((sr, sc), (row, col), self.board) \
                    and not self.board.is_path_blocked((sr, sc), (row, col), pt.is_jumper()) \
                    and not self._is_moving(sr, sc) \
                    and not self._is_destination_taken(row, col) \
                    and not self._route_conflicts((sr, sc), (row, col)):
                duration = self._travel_time((sr, sc), (row, col), pt)
                self.action_queue.append(Action((sr, sc), (row, col), self.current_time, duration))
                self.selected = None
            else:
                self.selected = None
        elif target != ".":
            self.selected = (row, col)

    def jump(self, x, y):
        """Schedule a jump (airborne) action for the piece at the given pixel coords."""
        if self.is_game_over():
            return
        col, row = x // 100, y // 100
        if not self.board.in_bounds(row, col):
            return
        # cannot jump from empty cell
        if self.board.get(row, col) == ".":
            return
        # cannot jump if piece is currently moving or already airborne
        if self._is_moving(row, col) or self._is_airborne(row, col):
            return
        # schedule jump action (start == end) with fixed duration
        self.action_queue.append(Action((row, col), (row, col), self.current_time, PieceRegistry.JUMP_DURATION_MS))

    def wait(self, ms):
        if self.is_game_over():
            return
        self.current_time += ms
        self._flush_actions()

    def is_game_over(self):
        return self.scores['w'] == float('inf') or self.scores['b'] == float('inf')
