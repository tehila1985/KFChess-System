"""
Phase 0 seam (.github/Server_Design_Implementation_Plan.md): keeps
AbstractUserRepository/AbstractGameRepository the only way any service
touches persistence, so Phase 4's Postgres swap only ever touches
server/repositories/ and server/db/.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.check_no_raw_sql import find_violations


def test_no_raw_sql_or_sqlite3_outside_repositories_and_db():
    root = Path(__file__).parent.parent.parent
    violations = find_violations(root)
    assert violations == [], "\n".join(violations)
