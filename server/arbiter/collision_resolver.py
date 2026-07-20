from __future__ import annotations
from server.arbiter.motion import ActiveMotion, CompletedMotion


class CollisionResolver:
    """
    Resolves completed motions into winners and losers.

    Owns all collision logic:
    - head-to-head: two pieces that swapped positions — the later starter loses
    - airborne: a jumping piece captures an enemy arriving at the same square

    RealTimeArbiter calls resolve() and then applies the results to the board.
    """

    def resolve(
        self,
        done: list[ActiveMotion],
    ) -> tuple[list[tuple[int, ActiveMotion]], set[int]]:
        """
        Returns (survivors, loser_indices).

        survivors: list of (index, motion) that should be placed on the board,
                   each paired with its captured piece (or None) via captured_for().
        loser_indices: indices into done that are eliminated without landing.
        """
        loser_indices: set[int] = set()
        captured_map: dict[int, ActiveMotion] = {}  # winner index -> captured motion

        # Phase 1: head-to-head
        for i, a in enumerate(done):
            for j, b in enumerate(done):
                if i >= j or a.is_jump or b.is_jump:
                    continue
                if a.dst == b.src and a.src == b.dst:
                    if b.start_time < a.start_time:
                        loser_indices.add(i)
                    else:
                        loser_indices.add(j)

        # Phase 2: airborne captures
        for i, motion in enumerate(done):
            if not motion.is_jump:
                continue
            for j, other in enumerate(done):
                if j in loser_indices or other.is_jump or other.dst != motion.src:
                    continue
                loser_indices.add(j)
                captured_map[i] = other

        return loser_indices, captured_map
