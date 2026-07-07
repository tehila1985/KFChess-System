import sys
import re

def parse_and_validate_board():
    input_data = sys.stdin.read().strip()
    if not input_data:
        return

    # חלוקה ללוח ופקודות
    lines = input_data.splitlines()
    board_lines = []
    found_board = False
    
    for line in lines:
        line = line.strip()
        if line == "Board:":
            found_board = True
            continue
        if line == "Commands:" or not line:
            break
        if found_board:
            board_lines.append(line)

    if not board_lines:
        return

    # בדיקת רוחב שורות (Test 5)
    width = len(board_lines[0].split())
    for row in board_lines:
        tokens = row.split()
        if len(tokens) != width:
            print("ERROR ROW_WIDTH_MISMATCH")
            return
        
        # בדיקת תווים חוקיים (Test 4)
        # תווים מותרים: wK, wQ, wR, wB, wN, wP, bK, bQ, bR, bB, bN, bP, ו- .
        for token in tokens:
            if token != "." and not re.match(r'^[wb][KQRBNP]$', token):
                print("ERROR UNKNOWN_TOKEN")
                return

    # אם הכל תקין, הדפסת הלוח (Test 2, 3)
    for row in board_lines:
        print(row)

if __name__ == "__main__":
    parse_and_validate_board()