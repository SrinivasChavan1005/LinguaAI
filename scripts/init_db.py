"""Create or upgrade the local SQLite database (safe to run many times)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import database_path  # noqa: E402
from database.database import DatabaseError, initialize  # noqa: E402

try:
    version = initialize()
except DatabaseError as exc:
    print(f"[FAIL] {exc}")
    sys.exit(1)
print(f"[ OK ] Database ready: {database_path()} (schema v{version})")
