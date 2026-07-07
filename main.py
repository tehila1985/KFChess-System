import sys
from step2 import GameRunner

if __name__ == "__main__":
    runner = GameRunner()
    runner.run(sys.stdin.read())