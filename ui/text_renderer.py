from engine.game_engine import GameSnapshot


class TextRenderer:
    """
    Renders a GameSnapshot as a plain-text string.
    Pure adapter — reads snapshot data, produces text, contains no logic.
    """

    def render(self, snapshot: GameSnapshot) -> str:
        return "\n".join(" ".join(row) for row in snapshot.grid)
