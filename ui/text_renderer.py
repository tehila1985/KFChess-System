from engine.game_engine import GameSnapshot


class TextRenderer:
    """
    Renders a GameSnapshot as a plain-text string.
    Pure adapter — reads snapshot data, produces text, contains no logic.
    """

    def render(self, snapshot: GameSnapshot) -> str:
        lines = []

        for row in snapshot.grid:
            lines.append(" ".join(row))

        lines.append(f"Score  w:{snapshot.scores.get('w', 0)}  b:{snapshot.scores.get('b', 0)}")

        if snapshot.game_over:
            lines.append(f"GAME OVER — winner: {snapshot.winner}")
        else:
            lines.append("Game in progress")

        return "\n".join(lines)
