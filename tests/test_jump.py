import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.board import Board
from engine.game_logic import GameEngine


class TestJumpBehavior(unittest.TestCase):

    def test_airborne_piece_captures_arriving_enemy(self):
        # airborne piece stays; arriving enemy is removed
        b = Board(['. . .', 'wK bR .', '. . .'])
        e = GameEngine(b)
        e.jump(50, 150)              # wK at (1,0) jumps
        e.click(150, 150); e.click(50, 150)  # bR moves to (1,0)
        e.wait(1000)
        self.assertEqual(b.get(1, 0), 'wK')
        self.assertEqual(b.get(1, 1), '.')

    def test_airborne_lands_if_no_arrival(self):
        # if no enemy arrives, jumper simply finishes its jump (remains in place)
        b = Board(['. . .', 'wK . .', '. . .'])
        e = GameEngine(b)
        e.jump(50, 150)
        e.wait(1000)
        self.assertEqual(b.get(1, 0), 'wK')

    def test_moving_piece_cannot_jump(self):
        # a piece that is currently moving cannot start a jump
        b = Board(['wR . .'])
        e = GameEngine(b)
        e.click(50, 50); e.click(250, 50)  # start move from (0,0) -> (0,2)
        e.jump(50, 50)  # attempt to jump while moving (should be ignored)
        e.wait(2000)
        self.assertEqual(b.get(0, 2), 'wR')


if __name__ == '__main__':
    unittest.main()
