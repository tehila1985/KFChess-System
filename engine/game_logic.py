from engine.pieces import PieceRegistry

MOVE_DURATION_MS = {
    'K': 1000,
    'Q': 1000,
    'R': 1000,
    'B': 1000,
    'N': 1000,
    'P': 1000,
}


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
        return any(a.start == (r, c) for a in self.action_queue)

    def _is_destination_taken(self, tr, tc):
        return any(a.end == (tr, tc) for a in self.action_queue)

    def _route_conflicts(self, start, end):
        """חוסם רק אם כלי אחר נע לאותה עמודה יעד מאותו כיוון (לא head-to-head)"""
        for a in self.action_queue:
            if a.end[1] == end[1] and a.start[1] != end[1]:
                # אותה עמודה יעד, ושניהם באים מאותו צד
                if (start[1] < end[1]) == (a.start[1] < a.end[1]):
                    return True
        return False

    def _travel_time(self, start, end, piece_type):
        return MOVE_DURATION_MS.get(piece_type.code, 1000)

    def _flush_actions(self):
        done = sorted(
            [a for a in self.action_queue if a.end_time <= self.current_time],
            key=lambda a: a.start_time
        )
        for action in done:
            self.action_queue.remove(action)

        winners = set()
        losers = set()
        for i, action in enumerate(done):
            for j, other in enumerate(done):
                if i == j:
                    continue
                # head-to-head: other נע לתא המקור של action
                if other.end == action.start and other.start == action.end:
                    if other.start_time < action.start_time:
                        losers.add(i)  # action התחיל אחר
                    elif other.start_time == action.start_time and j < i:
                        losers.add(i)  # זמן שווה — הראשון בסדר מנצח

        for i, action in enumerate(done):
            if i in losers:
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

    def wait(self, ms):
        if self.is_game_over():
            return
        self.current_time += ms
        self._flush_actions()

    def is_game_over(self):
        return self.scores['w'] == float('inf') or self.scores['b'] == float('inf')
