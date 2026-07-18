from __future__ import annotations

from pathlib import Path

from ui.vendor.img import Img


class SpriteLoader:
    """Loads sprites through Img.read while hiding asset path details."""

    def __init__(self, assets_root: Path) -> None:
        self._assets_root = assets_root

    def load(self, relative_path: str) -> Img:
        return Img.read(str(self._assets_root / relative_path))
