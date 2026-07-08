import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.board import Board
from engine.pieces import (
    KingRule, RookRule, BishopRule, QueenRule, KnightRule, PawnRule,
    PieceRegistry, MOVE_DURATION_MS, PIECE_SCORE
)


class TestKingRule(unittest.TestCase):

    def setUp(self):
        self.b = Board(['. . .', '. wK .', '. . .'])
        self.rule = KingRule()

    def test_move_one_step_valid(self):
        # בודק שמלך יכול לזוז משבצת אחת בכל כיוון
        self.assertTrue(self.rule.is_legal((1, 1), (0, 0), self.b))
        self.assertTrue(self.rule.is_legal((1, 1), (1, 2), self.b))

    def test_move_two_steps_invalid(self):
        # בודק שמלך לא יכול לזוז שתי משבצות
        self.assertFalse(self.rule.is_legal((1, 1), (1, 3), self.b))


class TestRookRule(unittest.TestCase):

    def setUp(self):
        self.b = Board(['wR . . .', '. . . .'])
        self.rule = RookRule()

    def test_horizontal_move_valid(self):
        # בודק תנועה אופקית חוקית
        self.assertTrue(self.rule.is_legal((0, 0), (0, 3), self.b))

    def test_vertical_move_valid(self):
        # בודק תנועה אנכית חוקית
        self.assertTrue(self.rule.is_legal((0, 0), (1, 0), self.b))

    def test_diagonal_move_invalid(self):
        # בודק שצריח לא יכול לזוז באלכסון
        self.assertFalse(self.rule.is_legal((0, 0), (1, 1), self.b))


class TestBishopRule(unittest.TestCase):

    def setUp(self):
        self.b = Board(['wB . .', '. . .', '. . .'])
        self.rule = BishopRule()

    def test_diagonal_move_valid(self):
        # בודק תנועה אלכסונית חוקית
        self.assertTrue(self.rule.is_legal((0, 0), (2, 2), self.b))

    def test_straight_move_invalid(self):
        # בודק שרץ לא יכול לזוז ישר
        self.assertFalse(self.rule.is_legal((0, 0), (0, 2), self.b))


class TestQueenRule(unittest.TestCase):

    def setUp(self):
        self.b = Board(['wQ . .', '. . .', '. . .'])
        self.rule = QueenRule()

    def test_horizontal_valid(self):
        # בודק תנועה אופקית של מלכה
        self.assertTrue(self.rule.is_legal((0, 0), (0, 2), self.b))

    def test_diagonal_valid(self):
        # בודק תנועה אלכסונית של מלכה
        self.assertTrue(self.rule.is_legal((0, 0), (2, 2), self.b))

    def test_invalid_move(self):
        # בודק תנועה לא חוקית של מלכה
        self.assertFalse(self.rule.is_legal((0, 0), (1, 2), self.b))


class TestKnightRule(unittest.TestCase):

    def setUp(self):
        self.b = Board(['wN . .', '. . .', '. . .'])
        self.rule = KnightRule()

    def test_l_shape_valid(self):
        # בודק תנועת L חוקית של פרש
        self.assertTrue(self.rule.is_legal((0, 0), (2, 1), self.b))
        self.assertTrue(self.rule.is_legal((0, 0), (1, 2), self.b))

    def test_straight_invalid(self):
        # בודק שפרש לא יכול לזוז ישר
        self.assertFalse(self.rule.is_legal((0, 0), (0, 2), self.b))

    def test_is_jumper(self):
        # בודק שפרש מוגדר כ-jumper
        self.assertTrue(self.rule.is_jumper())


class TestPawnRule(unittest.TestCase):

    def test_white_pawn_moves_up(self):
        # בודק שחייל לבן זז קדימה (למעלה)
        b = Board(['. . .', '. wP .', '. . .'])
        rule = PawnRule()
        self.assertTrue(rule.is_legal((1, 1), (0, 1), b))

    def test_white_pawn_cannot_move_down(self):
        # בודק שחייל לבן לא יכול לזוז אחורה
        b = Board(['. . .', '. wP .', '. . .'])
        rule = PawnRule()
        self.assertFalse(rule.is_legal((1, 1), (2, 1), b))

    def test_pawn_capture_diagonal(self):
        # בודק שחייל יכול לאכול באלכסון
        b = Board(['bR . .', '. wP .', '. . .'])
        rule = PawnRule()
        self.assertTrue(rule.is_legal((1, 1), (0, 0), b))

    def test_pawn_cannot_capture_own(self):
        # בודק שחייל לא יכול לאכול כלי שלו
        b = Board(['wR . .', '. wP .', '. . .'])
        rule = PawnRule()
        self.assertFalse(rule.is_legal((1, 1), (0, 0), b))


class TestPieceRegistry(unittest.TestCase):

    def test_all_pieces_registered(self):
        # בודק שכל 6 הכלים רשומים ב-Registry
        for code in ['K', 'Q', 'R', 'B', 'N', 'P']:
            self.assertIsNotNone(PieceRegistry.get(code))

    def test_unknown_piece_returns_none(self):
        # בודק שכלי לא קיים מחזיר None
        self.assertIsNone(PieceRegistry.get('X'))

    def test_piece_scores(self):
        # בודק שניקוד הכלים נכון
        self.assertEqual(PieceRegistry.get('Q').score, 9)
        self.assertEqual(PieceRegistry.get('R').score, 5)
        self.assertEqual(PieceRegistry.get('B').score, 3)
        self.assertEqual(PieceRegistry.get('N').score, 3)
        self.assertEqual(PieceRegistry.get('P').score, 1)
        self.assertEqual(PieceRegistry.get('K').score, float('inf'))

    def test_move_duration_defined(self):
        # בודק שכל הכלים מוגדרים ב-MOVE_DURATION_MS
        for code in ['K', 'Q', 'R', 'B', 'N', 'P']:
            self.assertIn(code, MOVE_DURATION_MS)

    def test_piece_score_dict(self):
        # בודק שמילון PIECE_SCORE מכיל את כל הכלים
        for code in ['K', 'Q', 'R', 'B', 'N', 'P']:
            self.assertIn(code, PIECE_SCORE)


if __name__ == '__main__':
    unittest.main()
