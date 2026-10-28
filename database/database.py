"""
SQLite database setup and schema migrations.

How data is stored
------------------
* One file: ``data/linguaai.db`` (on your computer only).
* ``sessions``   - one row per practice session (mode, scenario, start/end).
* ``turns``      - every message in a session (who spoke, text, speech metrics).
* ``feedback``   - grammar / session / pronunciation feedback as JSON, plus your
                   rating ("helpful", "wrong", "dismissed").
* ``vocabulary`` - your personal word list.
* ``practice_attempts`` - pronunciation and vocabulary-revision attempts.
* ``preferences`` - your learning profile (key -> JSON value).

No audio is stored. Deleting a session also deletes its turns and feedback
(``ON DELETE CASCADE``).

Migrations: SQLite's ``PRAGMA user_version`` stores the schema version. Each
entry in ``MIGRATIONS`` upgrades the database by one version, inside a
transaction, so an old database is upgraded safely when the app starts.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config.settings import database_path

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    pass


MIGRATIONS: list[str] = [
    # Version 1: initial schema
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        mode        TEXT NOT NULL,
        scenario    TEXT NOT NULL DEFAULT '',
        started_at  TEXT NOT NULL DEFAULT (datetime('now')),
        ended_at    TEXT
    );
    CREATE TABLE IF NOT EXISTS turns (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id       INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        text             TEXT NOT NULL,
        input_type       TEXT NOT NULL DEFAULT 'voice',
        created_at       TEXT NOT NULL DEFAULT (datetime('now')),
        recording_seconds REAL,
        speaking_seconds  REAL,
        word_count        INTEGER,
        words_per_minute  REAL,
        filler_count      INTEGER,
        long_pauses       INTEGER,
        metrics_json      TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
    CREATE TABLE IF NOT EXISTS feedback (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id   INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
        turn_id      INTEGER REFERENCES turns(id) ON DELETE CASCADE,
        kind         TEXT NOT NULL CHECK (kind IN ('grammar', 'session', 'pronunciation')),
        payload_json TEXT NOT NULL,
        user_rating  TEXT CHECK (user_rating IN ('helpful', 'wrong', 'dismissed')),
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);
    CREATE TABLE IF NOT EXISTS vocabulary (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        word              TEXT NOT NULL UNIQUE COLLATE NOCASE,
        definition        TEXT NOT NULL DEFAULT '',
        example           TEXT NOT NULL DEFAULT '',
        synonyms_json     TEXT NOT NULL DEFAULT '[]',
        usage             TEXT NOT NULL DEFAULT '',
        register          TEXT NOT NULL DEFAULT '',
        collocations_json TEXT NOT NULL DEFAULT '[]',
        practice_question TEXT NOT NULL DEFAULT '',
        notes             TEXT NOT NULL DEFAULT '',
        mastered          INTEGER NOT NULL DEFAULT 0,
        source            TEXT NOT NULL DEFAULT 'manual',
        review_count      INTEGER NOT NULL DEFAULT 0,
        correct_count     INTEGER NOT NULL DEFAULT 0,
        last_reviewed     TEXT,
        created_at        TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS practice_attempts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        kind        TEXT NOT NULL,
        reference   TEXT NOT NULL DEFAULT '',
        response    TEXT NOT NULL DEFAULT '',
        result_json TEXT NOT NULL DEFAULT '{}',
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS preferences (
        key        TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open a connection with safe settings. Each call returns a new connection."""
    path = Path(path) if path else database_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    except (sqlite3.Error, OSError) as exc:
        raise DatabaseError(f"Could not open the database at {path}: {exc}") from exc
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # safer with Streamlit's threads
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise DatabaseError(
            f"The database file {path} seems damaged ({exc}). Rename it to keep a copy; a new "
            "empty database will be created the next time LinguaAI starts."
        ) from exc
    return conn


def initialize(path: Path | None = None) -> int:
    """Create or upgrade the database. Returns the schema version."""
    conn = connect(path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise DatabaseError(
                f"The database was created by a newer LinguaAI (schema {version}). "
                "Please update the application."
            )
        for index in range(version, SCHEMA_VERSION):
            logger.info("Applying database migration %d", index + 1)
            try:
                conn.execute("BEGIN")
                for statement in _split_sql(MIGRATIONS[index]):
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {index + 1}")
                conn.execute("COMMIT")
            except sqlite3.Error as exc:
                conn.execute("ROLLBACK")
                raise DatabaseError(f"Database migration {index + 1} failed: {exc}") from exc
        return SCHEMA_VERSION
    except sqlite3.DatabaseError as exc:
        raise DatabaseError(
            f"The database file seems damaged ({exc}). Rename data\\linguaai.db to keep a copy; "
            "a new empty database will be created next time."
        ) from exc
    finally:
        conn.close()


def _split_sql(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]


@contextmanager
def transaction(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """``with transaction() as conn:`` commits on success, rolls back on error."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
