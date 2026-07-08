import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.validator import validate_board


class TestValidateBoardEmpty(unittest.TestCase):

    def test_empty_input_returns_false(self):
        # בודק שקלט ריק מחזיר False
        self.assertFalse(validate_board([]))


class TestValidateBoardValid(unittest.TestCase):

    def test_valid_board_returns_true(self):
        # בודק שלוח תקין מחזיר True
        result = validate_board(['wR . wK', '. . .', 'bR . bK'])
        self.assertTrue(result)

    def test_all_piece_types_valid(self):
        # בודק שכל סוגי הכלים החוקיים מתקבלים
        result = validate_board(['wK wQ wR wB wN wP'])
        self.assertTrue(result)

    def test_dots_are_valid(self):
        # בודק שנקודות (משבצות ריקות) מתקבלות
        result = validate_board(['. . .', '. . .'])
        self.assertTrue(result)


class TestValidateBoardErrors(unittest.TestCase):

    def test_row_width_mismatch(self):
        # בודק שחוסר אחידות ברוחב שורות מחזיר שגיאה
        result = validate_board(['wR . .', 'wR .'])
        self.assertEqual(result, 'ERROR ROW_WIDTH_MISMATCH')

    def test_unknown_token(self):
        # בודק שטוקן לא חוקי מחזיר שגיאה
        result = validate_board(['wR XX .'])
        self.assertEqual(result, 'ERROR UNKNOWN_TOKEN')

    def test_invalid_color_prefix(self):
        # בודק שצבע לא חוקי (לא w/b) מחזיר שגיאה
        result = validate_board(['xR . .'])
        self.assertEqual(result, 'ERROR UNKNOWN_TOKEN')

    def test_invalid_piece_letter(self):
        # בודק שאות כלי לא חוקית מחזירה שגיאה
        result = validate_board(['wX . .'])
        self.assertEqual(result, 'ERROR UNKNOWN_TOKEN')


if __name__ == '__main__':
    unittest.main()
