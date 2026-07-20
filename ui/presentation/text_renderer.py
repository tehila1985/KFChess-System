from server.game_engine import GameSnapshot


class TextRenderer:
    """
    Converts a GameSnapshot to printable text.

    Fully decoupled from the model, so it can be swapped with any other
    presentation layer without changing GameEngine.
    """

    def render(self, snapshot: GameSnapshot) -> str:
        """Full render: board + scores + game state."""
        scores = dict(snapshot.scores)
        lines = [" ".join(row) for row in snapshot.grid]
        lines.append(f"Score  w:{scores.get('w', 0)}  b:{scores.get('b', 0)}")
        if snapshot.game_over:
            lines.append(f"GAME OVER - winner: {snapshot.winner}")
        else:
            lines.append("Game in progress")
        return "\n".join(lines)

    def render_board_only(self, snapshot: GameSnapshot) -> str:
        """Renders board-only output used by CLI tests."""
        return "\n".join(" ".join(row) for row in snapshot.grid)
