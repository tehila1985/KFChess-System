from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DirtyState:
    dirty: bool = True

    def mark_dirty(self) -> None:
        self.dirty = True

    def clear(self) -> None:
        self.dirty = False
