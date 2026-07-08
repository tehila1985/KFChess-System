import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.board import Board
from engine.game_logic import GameEngine


class TestGameEngineSelection(unittest.TestCase):

    def test_select_piece(self):
        # בודק שלחיצה על כלי בוחרת אותו
        b = Board(['wR . .'])
        e = GameEngine(b)
        e.click(50, 50)
        self.assertEqual(e.selected, (0, 0))

    def test_select_empty_does_nothing(self):
        # בודק שלחיצה על משבצת ריקה לא בוחרת כלום
        b = Board(['wR . .'])
        e = GameEngine(b)
        e.click(150, 50)
        self.assertIsNone(e.selected)

    def test_reselect_own_piece(self):
        # בודק שלחיצה על כלי אחר מאותו צד מחליפה בחירה
        b = Board(['wR wK .'])
        e = GameEngine(b)
        e.click(50, 50)
        e.click(150, 50)
        self.assertEqual(e.selected, (0, 1))


class TestGameEngineMovement(unittest.TestCase):

    def test_piece_stays_during_travel(self):
        # בודק שהכלי נשאר במקומו לפני שהגיע ליעד
        b = Board(['wR . .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(150, 50)
        e.wait(500)
        self.assertEqual(b.get(0, 0), 'wR')

    def test_piece_arrives_after_duration(self):
        # בודק שהכלי מגיע ליעד אחרי זמן התנועה
        b = Board(['wR . .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(150, 50)
        e.wait(1000)
        self.assertEqual(b.get(0, 1), 'wR')
        self.assertEqual(b.get(0, 0), '.')

    def test_cannot_redirect_while_moving(self):
        # בודק שלא ניתן להפנות כלי שכבר בתנועה
        b = Board(['wR . .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(150, 50)
        e.click(50, 50); e.click(250, 50)
        e.wait(1000)
        self.assertEqual(b.get(0, 1), 'wR')

    def test_can_move_again_after_arrival(self):
        # בודק שכלי יכול לזוז שוב מיד אחרי הגעה (אין cooldown)
        b = Board(['wR . .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(150, 50); e.wait(1000)
        e.click(150, 50); e.click(250, 50); e.wait(1000)
        self.assertEqual(b.get(0, 2), 'wR')


class TestGameEngineBlocking(unittest.TestCase):

    def test_rook_blocked_by_own_piece(self):
        # בודק שצריח לא יכול לעבור דרך כלי שלו
        b = Board(['wR wP .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50); e.wait(2000)
        self.assertEqual(b.get(0, 0), 'wR')

    def test_bishop_blocked_by_own_piece(self):
        # בודק שרץ לא יכול לעבור דרך כלי שלו
        b = Board(['wB . .', '. wP .', '. . .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 250); e.wait(2000)
        self.assertEqual(b.get(0, 0), 'wB')

    def test_knight_jumps_over_blockers(self):
        # בודק שפרש יכול לקפוץ מעל כלים חוסמים
        b = Board(['wN wP .', 'wP . .', '. . .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(150, 250); e.wait(2000)
        self.assertEqual(b.get(2, 1), 'wN')

    def test_cannot_capture_own_piece(self):
        # בודק שלא ניתן לאכול כלי שלך
        b = Board(['wR . wP'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50); e.wait(2000)
        self.assertEqual(b.get(0, 0), 'wR')
        self.assertEqual(b.get(0, 2), 'wP')

    def test_opposite_colors_no_concurrent_route(self):
        # בודק ששני כלים מצבעים שונים לא יכולים לנוע לאותה עמודה יעד
        b = Board(['wR . .', '. . .', 'bR . .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50)
        e.click(50, 250); e.click(250, 250)
        e.wait(2000)
        self.assertEqual(b.get(0, 2), 'wR')
        self.assertEqual(b.get(2, 0), 'bR')


class TestGameEngineCapture(unittest.TestCase):

    def test_capture_enemy_piece(self):
        # בודק אכילת כלי יריב
        b = Board(['wR . bR'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50); e.wait(2000)
        self.assertEqual(b.get(0, 2), 'wR')
        self.assertEqual(b.get(0, 0), '.')

    def test_score_updated_on_capture(self):
        # בודק שהניקוד מתעדכן אחרי אכילה
        b = Board(['wR . bR'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50); e.wait(2000)
        self.assertEqual(e.scores['w'], 5)


class TestGameEngineGameOver(unittest.TestCase):

    def test_capture_king_ends_game(self):
        # בודק שאכילת מלך מסיימת את המשחק
        b = Board(['wR . bK'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50); e.wait(2000)
        self.assertTrue(e.is_game_over())

    def test_game_not_over_without_king_capture(self):
        # בודק שהמשחק לא נגמר לפני אכילת מלך
        b = Board(['wR . bR'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50); e.wait(2000)
        self.assertFalse(e.is_game_over())

    def test_commands_ignored_after_game_over(self):
        # בודק שפקודות מתעלמות אחרי סיום המשחק
        b = Board(['wR . bK'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50); e.wait(2000)
        e.click(250, 50); e.click(50, 50); e.wait(2000)
        self.assertEqual(b.get(0, 2), 'wR')

    def test_white_wins_by_capturing_black_king(self):
        # בודק שלבן מנצח כשאוכל את מלך השחור
        b = Board(['wR . bK'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50); e.wait(2000)
        self.assertEqual(e.scores['w'], float('inf'))

    def test_black_wins_by_capturing_white_king(self):
        # בודק שהשחור מנצח כשאוכל את מלך הלבן
        b = Board(['wK . bR'])
        e = GameEngine(b)
        e.click(250, 50); e.click(50, 50); e.wait(2000)
        self.assertTrue(e.is_game_over())
        self.assertEqual(e.scores['b'], float('inf'))


class TestGameEngineTiming(unittest.TestCase):

    def test_piece_not_arrived_before_duration(self):
        # בודק שכלי לא הגיע לפני זמן התנועה (wait 500ms מתוך 1000ms)
        b = Board(['wR . .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50); e.wait(500)
        self.assertEqual(b.get(0, 0), 'wR')

    def test_piece_arrived_after_duration(self):
        # בודק שכלי הגיע אחרי זמן התנועה (wait 2000ms)
        b = Board(['wR . .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50); e.wait(2000)
        self.assertEqual(b.get(0, 2), 'wR')


class TestGameEngineHeadOnCollision(unittest.TestCase):

    def test_white_started_first_wins(self):
        # בודק שלבן שהתחיל ראשון מנצח בהתנגשות head-to-head
        b = Board(['wR . . bR'])
        e = GameEngine(b)
        e.click(50, 50); e.click(350, 50)
        e.click(350, 50); e.click(50, 50)
        e.wait(3000)
        self.assertEqual(b.get(0, 3), 'wR')
        self.assertEqual(b.get(0, 0), '.')

    def test_black_started_first_wins(self):
        # בודק שהשחור שהתחיל ראשון מנצח בהתנגשות head-to-head
        b = Board(['wR . . bR'])
        e = GameEngine(b)
        e.click(350, 50); e.click(50, 50)
        e.click(50, 50); e.click(350, 50)
        e.wait(3000)
        self.assertEqual(b.get(0, 0), 'bR')
        self.assertEqual(b.get(0, 3), '.')

    def test_head_on_winner_gets_score(self):
        # בודק שהמנצח בהתנגשות מקבל ניקוד
        b = Board(['wR . . bR'])
        e = GameEngine(b)
        e.click(50, 50); e.click(350, 50)
        e.click(350, 50); e.click(50, 50)
        e.wait(3000)
        self.assertEqual(e.scores['w'], 5)


if __name__ == '__main__':
    unittest.main()
