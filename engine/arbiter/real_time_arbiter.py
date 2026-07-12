from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from engine.models.board import Board
from engine.models.piece import Piece
from engine.models.position import Position
from engine.config import GameConfig, DEFAULT_CONFIG


@dataclass(frozen=True)
class ActiveMotion:
    """
    תנועה פעילה שטרם הסתיימה.

    is_jump=True: הכלי "עף" מעל הלוח ונוחת באותה משבצת (src == dst).
    בזמן קפיצה הכלי עדיין נמצא על הלוח (לא נמחק מהגריד).
    בתנועה רגילה הכלי נמחק מ-src ברגע ה-start_motion.
    """
    piece:      Piece
    src:        Position
    dst:        Position
    start_time: int
    duration:   int
    is_jump:    bool = False

    @property
    def end_time(self) -> int:
        return self.start_time + self.duration


@dataclass(frozen=True)
class CompletedMotion:
    """תוצאת תנועה שהסתיימה — מוחזרת ל-GameEngine לטיפול בלכידה/קידום."""
    piece:    Piece
    src:      Position
    dst:      Position
    captured: Optional[Piece]  # הכלי שנלכד, או None


class RealTimeArbiter:
    """
    אחראי על ניהול כל התנועות הפעילות בו-זמנית.

    תפקידים:
    - שמירת רשימת ActiveMotion
    - קידום הזמן (advance_time) ופתרון תנועות שהסתיימו
    - זיהוי התנגשויות head-to-head (מי התחיל ראשון מנצח)
    - טיפול בקפיצות (כלי קופץ לוכד כלי מגיע)
    - חסימת route conflicts (שני כלים לאותה עמודה מאותו כיוון)

    לא מכיר כללי שחמט — זה תפקיד RuleEngine.
    """

    def __init__(self, board: Board, config: GameConfig = DEFAULT_CONFIG):
        self._board        = board
        self._config       = config
        self._current_time = 0
        self._motions: list[ActiveMotion] = []

    @property
    def current_time(self) -> int:
        return self._current_time

    @property
    def active_motions(self) -> list[ActiveMotion]:
        return list(self._motions)

    def start_motion(self, piece: Piece, src: Position, dst: Position, duration: int) -> None:
        """
        מתחיל תנועה חדשה.

        בודק route conflict לפני הכל — אם כלי אחר כבר הולך לאותה עמודה
        מאותו כיוון, התנועה נחסמת (מניעת שני כלים על אותו נתיב).
        הכלי נמחק מ-src מיד (הלוח מראה אותו כנע).
        """
        if self._route_conflicts(src, dst):
            return
        self._board.set_piece(src, None)
        self._motions.append(ActiveMotion(piece, src, dst, self._current_time, duration, is_jump=False))

    def start_jump(self, pos: Position) -> None:
        """
        מתחיל קפיצה — הכלי נשאר על הלוח אבל מסומן כ-airborne.
        בזמן הקפיצה הוא יכול ללכוד כלי אויב שמגיע לאותה משבצת.
        """
        piece = self._board.get_piece(pos)
        if piece is None:
            return
        self._motions.append(ActiveMotion(piece, pos, pos, self._current_time, self._config.jump_duration_ms, is_jump=True))

    def advance_time(self, delta_ms: int) -> list[CompletedMotion]:
        """מקדם את שעון הסימולציה ומפעיל פתרון תנועות שהסתיימו."""
        self._current_time += delta_ms
        return self._resolve()

    def _route_conflicts(self, src: Position, dst: Position) -> bool:
        """
        חוסם תנועה אם כלי אחר כבר נע לאותה עמודה יעד מאותו כיוון.

        מטרה: מניעת מצב שבו שני כלים "רצים" על אותו נתיב בו-זמנית.
        הבדיקה היא על עמודת היעד וכיוון התנועה (שמאל/ימין).
        """
        for m in self._motions:
            if m.is_jump:
                continue
            if m.dst.col == dst.col and m.src.col != dst.col:
                if (src.col < dst.col) == (m.src.col < m.dst.col):
                    return True
        return False

    def _resolve(self) -> list[CompletedMotion]:
        """
        פותר את כל התנועות שהגיעו ל-end_time <= current_time.

        סדר הפתרון:
        1. מיון לפי start_time (מי התחיל ראשון)
        2. head-to-head: שני כלים שהחליפו מקומות — המאוחר מפסיד
        3. קפיצות: כלי קופץ לוכד כלי אויב שמגיע לאותה משבצת
        4. תנועות רגילות: הכלי מונח ביעד, לוכד מה שיש שם
        """
        done = sorted(
            [m for m in self._motions if m.end_time <= self._current_time],
            key=lambda m: (m.start_time, self._motions.index(m)),
        )
        if not done:
            return []

        for m in done:
            self._motions.remove(m)

        # שלב 1: head-to-head — מי התחיל מאוחר יותר מפסיד
        loser_indices: set[int] = set()
        for i, a in enumerate(done):
            for j, b in enumerate(done):
                if i >= j or a.is_jump or b.is_jump:
                    continue
                if a.dst == b.src and a.src == b.dst:
                    if b.start_time < a.start_time:
                        loser_indices.add(i)
                    else:
                        loser_indices.add(j)

        results: list[CompletedMotion] = []

        # שלב 2: קפיצות — כלי קופץ לוכד כלי אויב שמגיע לאותה משבצת
        airborne = {i for i, m in enumerate(done) if m.is_jump}
        for i, motion in enumerate(done):
            if i not in airborne:
                continue
            for j, other in enumerate(done):
                if j in loser_indices or other.is_jump or other.dst != motion.src:
                    continue
                # הכלי המגיע נלכד על ידי הקופץ
                loser_indices.add(j)
                results.append(CompletedMotion(
                    piece    = motion.piece,
                    src      = motion.src,
                    dst      = motion.dst,
                    captured = other.piece,
                ))

        # שלב 3: תנועות רגילות — הנח ביעד ולכוד מה שיש שם
        for i, motion in enumerate(done):
            if i in loser_indices or motion.is_jump:
                continue

            captured = self._board.get_piece(motion.dst)
            self._board.set_piece(motion.dst, motion.piece)

            results.append(CompletedMotion(
                piece    = motion.piece,
                src      = motion.src,
                dst      = motion.dst,
                captured = captured,
            ))

        return results
