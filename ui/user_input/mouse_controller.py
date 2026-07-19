from __future__ import annotations

from ui.interaction.controller import Controller


class MouseController:
    """Translates pointer coordinates into controller click commands."""

    def __init__(self, controller: Controller) -> None:
        self._controller = controller

    def on_pointer(self, x: int, y: int):
        return self._controller.on_click(x, y)
