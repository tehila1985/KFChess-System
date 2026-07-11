from engine.game_engine import GameSnapshot


class TextRenderer:
    """
    הופך GameSnapshot לטקסט להדפסה.

    נפרד מהמודל לחלוטין — אפשר להחליף ב-GUI renderer
    בלי לגעת ב-GameEngine.
    """

    def render(self, snapshot: GameSnapshot) -> str:
        """הדפסה מלאה: לוח + ניקוד + מצב משחק."""
        lines = [" ".join(row) for row in snapshot.grid]
        lines.append(f"Score  w:{snapshot.scores.get('w', 0)}  b:{snapshot.scores.get('b', 0)}")
        if snapshot.game_over:
            lines.append(f"GAME OVER — winner: {snapshot.winner}")
        else:
            lines.append("Game in progress")
        return "\n".join(lines)

    def render_board_only(self, snapshot: GameSnapshot) -> str:
        """הדפסת הלוח בלבד — בשימוש פקודת 'print board' בטסטים."""
        return "\n".join(" ".join(row) for row in snapshot.grid)
