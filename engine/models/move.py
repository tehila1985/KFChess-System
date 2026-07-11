from dataclasses import dataclass
from engine.models.position import Position


# Move מייצגת בקשת תנועה: ממשבצת src למשבצת dst.
# אובייקט נתונים טהור — נוצר ב-Controller ומועבר ל-RuleEngine לאימות.
@dataclass(frozen=True)
class Move:
    src: Position
    dst: Position
