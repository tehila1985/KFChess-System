from __future__ import annotations

from dataclasses import dataclass

from engine.game_engine import GameSnapshot


@dataclass(frozen=True)
class FrozenSnapshot:
    """Immutable copy of a game snapshot for safe before/after comparisons."""

    grid: tuple[tuple[str, ...], ...]
    game_over: bool
    winner: str | None

    @classmethod
    def from_snapshot(cls, snapshot: GameSnapshot) -> "FrozenSnapshot":
        frozen_grid = tuple(tuple(cell for cell in row) for row in snapshot.grid)
        return cls(grid=frozen_grid, game_over=snapshot.game_over, winner=snapshot.winner)
