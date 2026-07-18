from __future__ import annotations

from ui.vendor.img import Img


class HudRenderer:
    """Draws UI overlays and side panels on top of a frame using Img."""

    def apply(self, frame: Img, hud_text: str = "") -> Img:
        if hud_text:
            frame.put_text(hud_text, 8, 20)
        return frame
