from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter


@dataclass
class AnimationClock:
    """Small helper that converts wall time into frame delta milliseconds."""

    _last: float | None = None

    def tick_ms(self) -> int:
        now = perf_counter()
        if self._last is None:
            self._last = now
            return 0
        delta = now - self._last
        self._last = now
        return max(0, int(delta * 1000))
