"""
check_no_raw_sql.py — Phase 0 lint seam (.github/Server_Design_Implementation_Plan.md).

Confirms AbstractUserRepository/AbstractGameRepository stay the *only* way
any service touches persistence: no module outside server/repositories/ or
server/db/ may import sqlite3 or call .execute(...) with a raw SQL string.

Run directly: `python scripts/check_no_raw_sql.py`
Also enforced automatically by tests/unit/test_lint_no_raw_sql_outside_repositories.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED_DIRS = ("server/repositories", "server/db")
SCAN_DIRS = ("server", "client", "common")

IMPORT_PATTERN = re.compile(r"^\s*(import sqlite3|from sqlite3\b)", re.MULTILINE)
EXECUTE_SQL_PATTERN = re.compile(
    r"\.execute\(\s*[\"'].*?\b(SELECT|INSERT|UPDATE|DELETE|CREATE TABLE)\b",
    re.IGNORECASE | re.DOTALL,
)


def _is_allowed(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(rel.startswith(allowed + "/") for allowed in ALLOWED_DIRS)


def find_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for scan_dir in SCAN_DIRS:
        base = root / scan_dir
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if _is_allowed(path, root):
                continue
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(root).as_posix()
            if IMPORT_PATTERN.search(text):
                violations.append(f"{rel}: imports sqlite3 directly")
            if EXECUTE_SQL_PATTERN.search(text):
                violations.append(f"{rel}: calls .execute() with a raw SQL string")
    return violations


def main() -> int:
    root = Path(__file__).parent.parent
    violations = find_violations(root)
    if violations:
        print("Raw SQL / sqlite3 usage found outside server/repositories/ and server/db/:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("OK — no raw SQL or sqlite3 usage outside server/repositories/ and server/db/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
