from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UIConfig:
    window_title: str = "Kung-Fu Chess"
    board_cell_px: int = 100
    sidebar_width_px: int = 280
    skin_name: str = "pieces3"


DEFAULT_UI_CONFIG = UIConfig()
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
