from engine.game_engine import GameSnapshot


class TextRenderer:
    def render(self, snapshot: GameSnapshot) -> str:
        lines = [" ".join(row) for row in snapshot.grid]
        lines.append(f"Score  w:{snapshot.scores.get('w', 0)}  b:{snapshot.scores.get('b', 0)}")
        if snapshot.game_over:
            lines.append(f"GAME OVER — winner: {snapshot.winner}")
        else:
            lines.append("Game in progress")
        return "\n".join(lines)

    def render_board_only(self, snapshot: GameSnapshot) -> str:
        return "\n".join(" ".join(row) for row in snapshot.grid)
