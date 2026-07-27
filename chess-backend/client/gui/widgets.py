"""
widgets.py — minimal cv2-drawn Button and TextField widgets.

Built on ui/vendor/img.py:Img (fill_rect/put_text) — the same drawing
primitives ui/rendering/renderers.py already uses for the HUD panels.
No new drawing dependency introduced; no native OS widgets available in a
cv2 window, so these are hand-rolled (click-to-focus, keystroke-driven).
"""
from __future__ import annotations

from dataclasses import dataclass

from ui.vendor.img import Img

_BG = (55, 55, 65)
_BG_HOVER = (75, 75, 90)
_BORDER = (120, 120, 140)
_TEXT = (230, 230, 235)
_LABEL = (180, 180, 190)
_FIELD_BG = (25, 25, 30)
_FIELD_BORDER_FOCUS = (100, 210, 255)
_FIELD_BORDER = (90, 90, 100)
_ERROR = (90, 90, 240)


def _border(canvas: Img, x: int, y: int, w: int, h: int, color, thickness: int = 2) -> None:
    canvas.fill_rect(x, y, w, thickness, color)
    canvas.fill_rect(x, y + h - thickness, w, thickness, color)
    canvas.fill_rect(x, y, thickness, h, color)
    canvas.fill_rect(x + w - thickness, y, thickness, h, color)


@dataclass
class Button:
    label: str
    x: int
    y: int
    w: int
    h: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def draw(self, canvas: Img) -> None:
        canvas.fill_rect(self.x, self.y, self.w, self.h, _BG)
        _border(canvas, self.x, self.y, self.w, self.h, _BORDER)
        text_y = self.y + self.h // 2 + 6
        canvas.put_text(self.label, self.x + 14, text_y, color_bgr=_TEXT, scale=0.65, thickness=2)


@dataclass
class TextField:
    x: int
    y: int
    w: int
    h: int
    label: str = ""
    value: str = ""
    mask: bool = False
    focused: bool = False
    max_len: int = 32

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def handle_key(self, key: int) -> bool:
        """Feed one keystroke while focused. Returns True on Enter (submit)."""
        if not self.focused or key == -1:
            return False
        if key in (13, 10):
            return True
        if key in (8, 127):
            self.value = self.value[:-1]
            return False
        if 32 <= key < 127 and len(self.value) < self.max_len:
            self.value += chr(key)
        return False

    def draw(self, canvas: Img) -> None:
        if self.label:
            canvas.put_text(self.label, self.x, self.y - 10, color_bgr=_LABEL, scale=0.5, thickness=1)
        canvas.fill_rect(self.x, self.y, self.w, self.h, _FIELD_BG)
        _border(canvas, self.x, self.y, self.w, self.h, _FIELD_BORDER_FOCUS if self.focused else _FIELD_BORDER)
        shown = "*" * len(self.value) if self.mask else self.value
        if self.focused:
            shown += "_"
        canvas.put_text(shown, self.x + 10, self.y + self.h // 2 + 6, color_bgr=_TEXT, scale=0.6, thickness=1)


def draw_error(canvas: Img, x: int, y: int, message: str) -> None:
    canvas.put_text(message, x, y, color_bgr=_ERROR, scale=0.55, thickness=1)
