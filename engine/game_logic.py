from engine.pieces import PieceRegistry


class Action:
    """
    מייצג פעולה יחידה של כלי בלוח - תנועה או קפיצה.
    כל פעולה מתחילה בזמן מסוים (start_time) וגדוליה (duration).
    """
    def __init__(self, start, end, start_time, duration):
        self.start = start
        self.end = end
        self.start_time = start_time
        self.duration = duration

    @property
    def end_time(self):
        """רגע בו הפעולה מסתיימת (start_time + duration)"""
        return self.start_time + self.duration

    @property
    def is_jump(self):
        """האם הפעולה היא קפיצה? קפיצה היא כאשר start == end (הכלי לא זז משום מקום)"""
        return self.start == self.end


class GameEngine:
    """
    מנוע המשחק - אחראי על:
    - ניהול קיו של פעולות (action_queue)
    - עדכון זמן המשחק (current_time)
    - חישוב התנגשויות וקביעת הזוכים
    - ניהול הניקוד של שחקנים
    """
    def __init__(self, board):
        self.board = board                          # ההשתקפות הנוכחית של הלוח
        self.selected = None                        # הכלי שנבחר להזזה (מיקום: (row, col))
        self.current_time = 0                       # הזמן הנוכחי של סימולציה המשחק
        self.action_queue = []                      # רשימת כל הפעולות הפעילות (תנועות וקפיצות)
        self.scores = {'w': 0, 'b': 0}              # ניקוד כל שחקן לפי ערכי הכלים שנלכדו

    def _piece_type(self, r, c):
        """קבל את סוג הכלי במיקום (r, c). מחזיר PieceType או None אם תא ריק"""
        token = self.board.get(r, c)
        if token == ".":
            return None
        return PieceRegistry.get(token[1])

    def _is_moving(self, r, c):
        """בדוק אם הכלי במיקום (r, c) כרגע בדרך (בתנועה רגילה, לא קפיצה)"""
        return any(a.start == (r, c) and not a.is_jump for a in self.action_queue)

    def _is_airborne(self, r, c):
        """בדוק אם הכלי במיקום (r, c) כרגע קופץ (בקפיצה הגנתית)"""
        return any(a.is_jump and a.start == (r, c) for a in self.action_queue)

    def _is_destination_taken(self, tr, tc):
        """בדוק אם היעד (tr, tc) כבר שמור על ידי כלי אחר (בתנועה רגילה בלבד)"""
        return any(a.end == (tr, tc) and not a.is_jump for a in self.action_queue)

    def _route_conflicts(self, start, end):
        """
        בדוק אם יש כלי אחר שנע לאותה עמודה יעד מאותו כיוון.
        זה חוסם רק תנועות "מצד שונה", לא head-to-head.
        מונע צפיפות של כלים בעמודה אחת.
        """
        for a in self.action_queue:
            if a.end[1] == end[1] and a.start[1] != end[1]:
                # אותה עמודה יעד, ושניהם באים מאותו צד
                if (start[1] < end[1]) == (a.start[1] < a.end[1]):
                    return True
        return False

    def _travel_time(self, start, end, piece_type):
        """
        חשב את זמן התנועה עבור כלי מסוג מסוים.
        כל סוג כלי יש זמן תנועה שונה (מהלומה, כלי כבד נע יותר לאט).
        """
        return PieceRegistry.MOVE_DURATION_MS.get(piece_type.code, 1000)

    def _flush_actions(self):
        """
        ⚡ **הלב של המנוע** - מעבדת את כל הפעולות שיצרו מפוקסות.
        
        זרימה:
        1. אסוף את כל הפעולות שהסתיימו בזמן הנוכחי
        2. סדר אותן לפי start_time (כדי להתייחס להן בסדר הנכון)
        3. זהה head-to-head collisions (שני כלים חוצים אחד את השני)
        4. פתור קפיצות שתופסות כלים מגיעים
        5. פתור תנועות רגילות עם לכידות
        6. טפל בקידום חיילים (promotion)
        
        זה מה שמבדיל בין "תנועות מתוזמנות" ל"משחק עם כללים"!
        """
        # אסוף פעולות שסיימו (end_time <= current_time)
        done = sorted(
            [a for a in self.action_queue if a.end_time <= self.current_time],
            key=lambda a: a.start_time
        )
        # הסר אותן מהתור
        for action in done:
            if action in self.action_queue:
                self.action_queue.remove(action)

        # שמור "תמונת מצב" של הלוח לפני כל השינויים - נצטרך אותה לבדיקת התנגשויות
        snapshot = [row[:] for row in self.board.grid]

        # ⚔️ שלב 1: זהה head-to-head collisions
        # אם כלי A עובר ל-B.start וכלי B עובר ל-A.start, יש head-to-head
        # הזוכה הוא מי שהחל ראשון. אם בו-זמנית (start_time), המדד הוא j קטן יותר
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

        # 🦘 שלב 2: פתור קפיצות תופסות כלים מגיעים
        # אם כלי קופץ (is_jump) במקומו, וכלי אחר מגיע אליו, הקופץ אוכל את המגיע
        for i, action in enumerate(done):
            if i in losers or not action.is_jump:
                continue
            sr, sc = action.start
            if snapshot[sr][sc] == ".":
                continue
            # חפש כלי שמגיע אל הקופץ
            for j, other in enumerate(done):
                if j in losers or other is action or other.is_jump:
                    continue
                if other.end == action.start:
                    osr, osc = other.start
                    captured_token = snapshot[osr][osc]
                    if captured_token == ".":
                        continue
                    # הכלי המגיע לא מגיע לעולם - הוא נתפס בדרך!
                    self.board.set(osr, osc, ".")
                    # הקופץ מקבל את הנקודות (כי הכלי המגיע הוא של האויב)
                    pt = PieceRegistry.get(captured_token[1])
                    if pt:
                        winner = 'w' if captured_token[0] == 'b' else 'b'
                        self.scores[winner] += pt.score

        # 🚀 שלב 3: פתור תנועות רגילות (כלים שנעים למשבצת אחרת)
        for i, action in enumerate(done):
            if i in losers or action.is_jump:
                continue
            sr, sc = action.start
            if self.board.get(sr, sc) == ".":
                continue
            # בצע את התנועה והחזר מה שנלכד (אם יש)
            captured = self.board.move_piece(action.start, action.end)
            # אם תפסנו כלי, הוסף נקודות
            if captured != ".":
                pt = PieceRegistry.get(captured[1])
                if pt:
                    winner = 'w' if captured[0] == 'b' else 'b'
                    self.scores[winner] += pt.score
            # 👑 שלב 4: בדוק אם חייל הגיע לקצה הלוח - קדום ל-Queen
            tr, tc = action.end
            token = self.board.get(tr, tc)
            if token and token[1] == 'P':
                color = token[0]
                promotion_row = 0 if color == 'w' else self.board.rows - 1
                if tr == promotion_row:
                    self.board.set(tr, tc, color + 'Q')

    def click(self, x, y):
        """
        טופל בקליק של השחקן על הלוח.
        
        לוגיקה:
        1. אם כלי עדיין לא נבחר - בחר את הכלי בקליק זה (אם לא ריק)
        2. אם כלי כבר נבחר:
           - אם קליקו על כלי שלהם - החלף בחירה
           - אם קליקו על תא ריק או כלי יריב - בדוק אם הזזה חוקית וביצע
        3. בדיקות חוקיות: תנועה חוקית, נתיב פנוי, אין תנועה כרגע, יעד לא תפוס, אין conflict עמודה
        """
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

            # אם קליקו על כלי שלהם - החלף בחירה
            if target != "." and target[0] == p_token[0]:
                self.selected = (row, col)
                return

            # בדוק אם ההזזה חוקית בכל ההיבטים
            if pt and pt.is_legal_move((sr, sc), (row, col), self.board) \
                    and not self.board.is_path_blocked((sr, sc), (row, col), pt.is_jumper()) \
                    and not self._is_moving(sr, sc) \
                    and not self._is_destination_taken(row, col) \
                    and not self._route_conflicts((sr, sc), (row, col)):
                # התנועה חוקית! שנה אותה לקיו
                duration = self._travel_time((sr, sc), (row, col), pt)
                self.action_queue.append(Action((sr, sc), (row, col), self.current_time, duration))
                self.selected = None
            else:
                self.selected = None
        elif target != ".":
            # בחר כלי זה
            self.selected = (row, col)

    def jump(self, x, y):
        """
        טופל בקפיצה הגנתית של השחקן.
        
        קפיצה = כלי "קופץ במקום" - הוא נשאר באותה משבצת אבל נמצא "באויר" למשך זמן קצר.
        זה דרך להימנע מתקיפה נכנסת.
        
        כללים:
        - אי אפשר לקפוץ מתא ריק
        - אי אפשר לקפוץ אם הכלי כבר בדרך
        - אי אפשר לקפוץ אם הכלי כבר קופץ (לא ניתן להיות בשתי קפיצות בו-זמנית)
        """
        if self.is_game_over():
            return
        col, row = x // 100, y // 100
        if not self.board.in_bounds(row, col):
            return
        # בדוק שהתא לא ריק
        if self.board.get(row, col) == ".":
            return
        # בדוק שהכלי לא בתנועה כבר
        if self._is_moving(row, col) or self._is_airborne(row, col):
            return
        # שנה קפיצה - שזו Action עם start == end
        self.action_queue.append(Action((row, col), (row, col), self.current_time, PieceRegistry.JUMP_DURATION_MS))

    def wait(self, ms):
        """
        הליכת זמן - מקדם את הסימולציה.
        
        זה מה שגורם לפעולות להתרחש!
        כל פעם שקוראים ל-wait, אנחנו:
        1. מגבירים את current_time
        2. בודקים אילו פעולות סיימו (end_time <= current_time)
        3. מטמנים אותן בלוח (flush_actions)
        """
        if self.is_game_over():
            return
        self.current_time += ms
        self._flush_actions()

    def is_game_over(self):
        """בדוק אם המשחק הסתיים - כשנחה של אחד הצדדים הוא ∞ (כלומר המלך נלכד)"""
        return self.scores['w'] == float('inf') or self.scores['b'] == float('inf')
