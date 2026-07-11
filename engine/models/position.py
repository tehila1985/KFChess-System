from dataclasses import dataclass


# Position מייצגת כתובת תא בלוח.
# frozen=True — אי-אפשר לשנות אחרי יצירה, בטוח לשימוש כ-key ב-dict/set.
@dataclass(frozen=True)
class Position:
    row: int  # שורה (0 = שורה עליונה)
    col: int  # עמודה (0 = עמודה שמאלית)
