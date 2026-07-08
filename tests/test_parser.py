import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.parser import parse_input


class TestParseInput(unittest.TestCase):

    def test_parses_board_lines(self):
        # בודק שהפרסר מחלץ נכון את שורות הלוח
        inp = 'Board:\nwR . .\n. . .\nCommands:\nprint board'
        board_lines, _ = parse_input(inp)
        self.assertEqual(board_lines, ['wR . .', '. . .'])

    def test_parses_commands(self):
        # בודק שהפרסר מחלץ נכון את הפקודות
        inp = 'Board:\nwR . .\nCommands:\nclick 50 50\nwait 1000\nprint board'
        _, commands = parse_input(inp)
        self.assertEqual(commands, ['click 50 50', 'wait 1000', 'print board'])

    def test_empty_input(self):
        # בודק שקלט ריק מחזיר רשימות ריקות
        board_lines, commands = parse_input('')
        self.assertEqual(board_lines, [])
        self.assertEqual(commands, [])

    def test_ignores_blank_lines(self):
        # בודק שהפרסר מתעלם משורות ריקות
        inp = 'Board:\n\nwR . .\n\nCommands:\n\nclick 50 50'
        board_lines, commands = parse_input(inp)
        self.assertEqual(board_lines, ['wR . .'])
        self.assertEqual(commands, ['click 50 50'])

    def test_no_commands_section(self):
        # בודק שקלט ללא Commands מחזיר פקודות ריקות
        inp = 'Board:\nwR . .'
        board_lines, commands = parse_input(inp)
        self.assertEqual(board_lines, ['wR . .'])
        self.assertEqual(commands, [])

    def test_strips_whitespace(self):
        # בודק שהפרסר מסיר רווחים מיותרים
        inp = '  Board:  \n  wR . .  \n  Commands:  \n  click 50 50  '
        board_lines, commands = parse_input(inp)
        self.assertEqual(board_lines, ['wR . .'])
        self.assertEqual(commands, ['click 50 50'])


if __name__ == '__main__':
    unittest.main()
