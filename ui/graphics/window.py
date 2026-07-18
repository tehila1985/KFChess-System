from __future__ import annotations


class Window:
    """Thin window abstraction for future Img-backed display loop."""

    def __init__(self, title: str) -> None:
        self.title = title
        self._is_open = True

    @property
    def is_open(self) -> bool:
        return self._is_open

    def poll(self) -> None:
        return None

    def close(self) -> None:
        self._is_open = False
