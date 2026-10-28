"""
Read-only system diagnostics (used by check_system.bat).
Prints a report; never changes or deletes anything.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.system_checks import run_all_checks  # noqa: E402

SYMBOL = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]", "info": "[INFO]"}


def main() -> int:
    print("=" * 70)
    print(" LinguaAI system check (read-only)")
    print("=" * 70)
    checks = run_all_checks()
    for c in checks:
        print(f"{SYMBOL[c.status]} {c.name}: {c.detail}")
        if c.fix:
            print(f"        -> {c.fix}")
    failures = [c for c in checks if c.status == "fail"]
    print("-" * 70)
    if failures:
        print(f"{len(failures)} problem(s) found. See the '->' hints above or docs\\TROUBLESHOOTING.md")
        return 1
    print("Everything needed is in place.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
