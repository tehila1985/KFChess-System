import sys
from server.game_runner import GameRunner

if __name__ == "__main__":
    runner = GameRunner()
    runner.run(sys.stdin)