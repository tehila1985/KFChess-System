import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.board import Board


class TestBoardInit(unittest.TestCase):

    def test_grid_parsed_correctly(self):
        # בודק שהלוח מפורסר נכון משורות טקסט
        b = Board(['wR . .', '. wK .', '. . bR'])
        self.assertEqual(b.grid[0], ['wR', '.', '.'])
        self.assertEqual(b.grid[1], ['.', 'wK', '.'])
        self.assertEqual(b.grid[2], ['.', '.', 'bR'])

    def test_rows_and_cols(self):
        # בודק שמידות הלוח נקראות נכון
        b = Board(['wR . .', '. . .'])
        self.assertEqual(b.rows, 2)
        self.assertEqual(b.cols, 3)


class TestBoardInBounds(unittest.TestCase):

    def test_valid_position(self):
        # בודק שמשבצת בתוך הלוח מוכרת כחוקית
        b = Board(['wR . .', '. . .'])
        self.assertTrue(b.in_bounds(0, 0))
        self.assertTrue(b.in_bounds(1, 2))

    def test_out_of_bounds(self):
        # בודק שמשבצת מחוץ לגבולות מוכרת כלא חוקית
        b = Board(['wR . .', '. . .'])
        self.assertFalse(b.in_bounds(-1, 0))
        self.assertFalse(b.in_bounds(2, 0))
        self.assertFalse(b.in_bounds(0, 3))


class TestBoardGetSet(unittest.TestCase):

    def test_get_piece(self):
        # בודק קריאת ערך ממשבצת
        b = Board(['wR . .'])
        self.assertEqual(b.get(0, 0), 'wR')
        self.assertEqual(b.get(0, 1), '.')

    def test_set_piece(self):
        # בודק כתיבת ערך למשבצת
        b = Board(['wR . .'])
        b.set(0, 1, 'bK')
        self.assertEqual(b.get(0, 1), 'bK')

    def test_is_empty(self):
        # בודק זיהוי משבצת ריקה
        b = Board(['wR . .'])
        self.assertFalse(b.is_empty(0, 0))
        self.assertTrue(b.is_empty(0, 1))


class TestBoardPathBlocked(unittest.TestCase):

    def test_clear_path(self):
        # בודק שנתיב פנוי לא נחסם
        b = Board(['wR . . .'])
        self.assertFalse(b.is_path_blocked((0, 0), (0, 3)))

    def test_blocked_path(self):
        # בודק שנתיב עם כלי באמצע נחסם
        b = Board(['wR wP . .'])
        self.assertTrue(b.is_path_blocked((0, 0), (0, 3)))

    def test_jumper_ignores_blocks(self):
        # בודק שפרש (jumper) מתעלם מחסימות
        b = Board(['wN wP wP .'])
        self.assertFalse(b.is_path_blocked((0, 0), (0, 3), is_jumper=True))


class TestBoardMovePiece(unittest.TestCase):

    def test_simple_move(self):
        # בודק תנועה פשוטה למשבצת ריקה
        b = Board(['wR . .'])
        b.move_piece((0, 0), (0, 2))
        self.assertEqual(b.get(0, 0), '.')
        self.assertEqual(b.get(0, 2), 'wR')

    def test_capture_returns_captured(self):
        # בודק שאכילה מחזירה את הכלי שנאכל
        b = Board(['wR . bR'])
        captured = b.move_piece((0, 0), (0, 2))
        self.assertEqual(captured, 'bR')
        self.assertEqual(b.get(0, 2), 'wR')

    def test_move_to_empty_returns_dot(self):
        # בודק שתנועה למשבצת ריקה מחזירה נקודה
        b = Board(['wR . .'])
        captured = b.move_piece((0, 0), (0, 1))
        self.assertEqual(captured, '.')


if __name__ == '__main__':
    unittest.main()
