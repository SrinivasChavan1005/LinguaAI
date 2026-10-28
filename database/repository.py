"""
All database reads and writes. Every query uses ``?`` placeholders
(parameterised queries), so user text can never change the SQL itself.

Functions take an optional ``db_path`` so tests can use a temporary database.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from database.database import transaction

VALID_RATINGS = {"helpful", "wrong", "dismissed", None}


def _rows(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- sessions
def create_session(mode: str, scenario: str, db_path: Path | None = None) -> int:
    with transaction(db_path) as conn:
        cur = conn.execute("INSERT INTO sessions (mode, scenario) VALUES (?, ?)", (mode, scenario))
        return int(cur.lastrowid)


def end_session(session_id: int, db_path: Path | None = None) -> None:
    with transaction(db_path) as conn:
        conn.execute("UPDATE sessions SET ended_at = datetime('now') WHERE id = ? AND ended_at IS NULL",
                     (session_id,))


def list_sessions(limit: int = 200, db_path: Path | None = None) -> list[dict]:
    with transaction(db_path) as conn:
        return _rows(conn.execute(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id AND t.role = 'user') AS user_turns,
                      (SELECT COALESCE(SUM(word_count), 0) FROM turns t WHERE t.session_id = s.id AND t.role = 'user') AS words,
                      (SELECT COALESCE(SUM(recording_seconds), 0) FROM turns t WHERE t.session_id = s.id) AS seconds
               FROM sessions s ORDER BY s.id DESC LIMIT ?""", (limit,)))


def get_session(session_id: int, db_path: Path | None = None) -> dict | None:
    with transaction(db_path) as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


def delete_session(session_id: int, db_path: Path | None = None) -> None:
    with transaction(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def delete_empty_sessions(db_path: Path | None = None) -> int:
    with transaction(db_path) as conn:
        cur = conn.execute("""DELETE FROM sessions WHERE ended_at IS NOT NULL AND id NOT IN
                              (SELECT DISTINCT session_id FROM turns WHERE role = 'user')""")
        return cur.rowcount


# ------------------------------------------------------------------- turns
def add_turn(session_id: int, role: str, text: str, input_type: str = "voice",
             metrics: dict | None = None, db_path: Path | None = None) -> int:
    m = metrics or {}
    with transaction(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO turns (session_id, role, text, input_type, recording_seconds,
                   speaking_seconds, word_count, words_per_minute, filler_count, long_pauses, metrics_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, role, text, input_type, m.get("recording_seconds"), m.get("speaking_seconds"),
             m.get("word_count"), m.get("words_per_minute"), m.get("filler_count"),
             m.get("long_pauses"), json.dumps(m) if m else None))
        return int(cur.lastrowid)


def get_turns(session_id: int, db_path: Path | None = None) -> list[dict]:
    with transaction(db_path) as conn:
        return _rows(conn.execute("SELECT * FROM turns WHERE session_id = ? ORDER BY id", (session_id,)))


# ---------------------------------------------------------------- feedback
def add_feedback(kind: str, payload: dict, session_id: int | None = None, turn_id: int | None = None,
                 db_path: Path | None = None) -> int:
    with transaction(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO feedback (session_id, turn_id, kind, payload_json) VALUES (?, ?, ?, ?)",
            (session_id, turn_id, kind, json.dumps(payload)))
        return int(cur.lastrowid)


def rate_feedback(feedback_id: int, rating: str | None, db_path: Path | None = None) -> None:
    if rating not in VALID_RATINGS:
        raise ValueError(f"Invalid rating {rating!r}")
    with transaction(db_path) as conn:
        conn.execute("UPDATE feedback SET user_rating = ? WHERE id = ?", (rating, feedback_id))


def get_feedback(session_id: int | None = None, kind: str | None = None, limit: int = 500,
                 db_path: Path | None = None) -> list[dict]:
    sql, params = "SELECT * FROM feedback WHERE 1=1", []
    if session_id is not None:
        sql += " AND session_id = ?"
        params.append(session_id)
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with transaction(db_path) as conn:
        rows = _rows(conn.execute(sql, params))
    for r in rows:
        try:
            r["payload"] = json.loads(r["payload_json"])
        except (TypeError, ValueError):
            r["payload"] = {}
    return rows


# -------------------------------------------------------------- vocabulary
def save_word(entry: dict, source: str = "manual", db_path: Path | None = None) -> int:
    """Insert or update a word (matching is case-insensitive)."""
    word = str(entry.get("word", "")).strip()
    if not word:
        raise ValueError("Word is empty")
    values = (word, entry.get("definition", ""), entry.get("example", ""),
              json.dumps(entry.get("synonyms", [])), entry.get("usage", ""), entry.get("register", ""),
              json.dumps(entry.get("collocations", [])), entry.get("practice_question", ""), source)
    with transaction(db_path) as conn:
        conn.execute(
            """INSERT INTO vocabulary (word, definition, example, synonyms_json, usage, register,
                   collocations_json, practice_question, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(word) DO UPDATE SET definition=excluded.definition, example=excluded.example,
                   synonyms_json=excluded.synonyms_json, usage=excluded.usage, register=excluded.register,
                   collocations_json=excluded.collocations_json,
                   practice_question=excluded.practice_question""", values)
        row = conn.execute("SELECT id FROM vocabulary WHERE word = ?", (word,)).fetchone()
        return int(row["id"])


def list_words(only_unmastered: bool = False, db_path: Path | None = None) -> list[dict]:
    sql = "SELECT * FROM vocabulary"
    if only_unmastered:
        sql += " WHERE mastered = 0"
    sql += " ORDER BY created_at DESC, id DESC"
    with transaction(db_path) as conn:
        rows = _rows(conn.execute(sql))
    for r in rows:
        for key in ("synonyms", "collocations"):
            try:
                r[key] = json.loads(r.pop(f"{key}_json") or "[]")
            except ValueError:
                r[key] = []
    return rows


def update_word(word_id: int, *, notes: str | None = None, mastered: bool | None = None,
                db_path: Path | None = None) -> None:
    with transaction(db_path) as conn:
        if notes is not None:
            conn.execute("UPDATE vocabulary SET notes = ? WHERE id = ?", (notes[:2000], word_id))
        if mastered is not None:
            conn.execute("UPDATE vocabulary SET mastered = ? WHERE id = ?", (int(mastered), word_id))


def record_review(word_id: int, correct: bool, db_path: Path | None = None) -> None:
    with transaction(db_path) as conn:
        conn.execute("""UPDATE vocabulary SET review_count = review_count + 1,
                        correct_count = correct_count + ?, last_reviewed = datetime('now')
                        WHERE id = ?""", (int(correct), word_id))


def delete_word(word_id: int, db_path: Path | None = None) -> None:
    with transaction(db_path) as conn:
        conn.execute("DELETE FROM vocabulary WHERE id = ?", (word_id,))


# ------------------------------------------------------- practice attempts
def add_attempt(kind: str, reference: str, response: str, result: dict,
                db_path: Path | None = None) -> int:
    with transaction(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO practice_attempts (kind, reference, response, result_json) VALUES (?, ?, ?, ?)",
            (kind, reference, response, json.dumps(result)))
        return int(cur.lastrowid)


def list_attempts(kind: str | None = None, limit: int = 200, db_path: Path | None = None) -> list[dict]:
    with transaction(db_path) as conn:
        if kind:
            rows = conn.execute("SELECT * FROM practice_attempts WHERE kind = ? ORDER BY id DESC LIMIT ?",
                                (kind, limit))
        else:
            rows = conn.execute("SELECT * FROM practice_attempts ORDER BY id DESC LIMIT ?", (limit,))
        out = _rows(rows)
    for r in out:
        try:
            r["result"] = json.loads(r["result_json"])
        except ValueError:
            r["result"] = {}
    return out


# ------------------------------------------------------------- preferences
def get_preference(key: str, default: Any = None, db_path: Path | None = None) -> Any:
    with transaction(db_path) as conn:
        row = conn.execute("SELECT value_json FROM preferences WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value_json"])
    except ValueError:
        return default


def set_preference(key: str, value: Any, db_path: Path | None = None) -> None:
    with transaction(db_path) as conn:
        conn.execute("""INSERT INTO preferences (key, value_json, updated_at) VALUES (?, ?, datetime('now'))
                        ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json,
                        updated_at = excluded.updated_at""", (key, json.dumps(value)))


# ------------------------------------------------------- stats and export
def user_turn_metrics(db_path: Path | None = None) -> list[dict]:
    """All user turns with their session date and mode (for progress charts)."""
    with transaction(db_path) as conn:
        return _rows(conn.execute(
            """SELECT t.id, t.session_id, t.created_at, t.input_type, t.recording_seconds,
                      t.speaking_seconds, t.word_count, t.words_per_minute, t.filler_count,
                      t.long_pauses, t.metrics_json, s.mode, s.scenario
               FROM turns t JOIN sessions s ON s.id = t.session_id
               WHERE t.role = 'user' ORDER BY t.id"""))


def export_all(db_path: Path | None = None) -> dict[str, list[dict]]:
    with transaction(db_path) as conn:
        return {table: _rows(conn.execute(f"SELECT * FROM {table} ORDER BY id"))  # table names are constants
                for table in ("sessions", "turns", "feedback", "vocabulary", "practice_attempts")}


def delete_all_history(include_vocabulary: bool = False, db_path: Path | None = None) -> None:
    with transaction(db_path) as conn:
        conn.execute("DELETE FROM feedback")
        conn.execute("DELETE FROM turns")
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM practice_attempts")
        if include_vocabulary:
            conn.execute("DELETE FROM vocabulary")
