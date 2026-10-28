"""Database initialisation, migrations, persistence and deletion."""

import sqlite3

import pytest

from database import repository
from database.database import SCHEMA_VERSION, DatabaseError, initialize


def test_initialize_is_idempotent(tmp_path):
    path = tmp_path / "x.db"
    assert initialize(path) == SCHEMA_VERSION
    assert initialize(path) == SCHEMA_VERSION
    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"sessions", "turns", "feedback", "vocabulary", "practice_attempts", "preferences"} <= tables


def test_newer_schema_is_rejected(tmp_path):
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    conn.close()
    with pytest.raises(DatabaseError):
        initialize(path)


def test_corrupted_file_gives_clear_error(tmp_path):
    path = tmp_path / "bad.db"
    path.write_bytes(b"this is not a database" * 100)
    with pytest.raises(DatabaseError):
        initialize(path)


def test_conversation_persistence_and_cascade(db_path):
    sid = repository.create_session("daily", "Hobbies", db_path=db_path)
    t1 = repository.add_turn(sid, "assistant", "Hi!", db_path=db_path)
    t2 = repository.add_turn(sid, "user", "I like football.",
                             metrics={"word_count": 3, "words_per_minute": 120.0}, db_path=db_path)
    fid = repository.add_feedback("grammar", {"issues": []}, session_id=sid, turn_id=t2, db_path=db_path)
    repository.rate_feedback(fid, "helpful", db_path=db_path)
    turns = repository.get_turns(sid, db_path=db_path)
    assert [t["id"] for t in turns] == [t1, t2]
    assert turns[1]["word_count"] == 3
    assert repository.get_feedback(session_id=sid, db_path=db_path)[0]["user_rating"] == "helpful"
    sessions = repository.list_sessions(db_path=db_path)
    assert sessions[0]["user_turns"] == 1 and sessions[0]["words"] == 3

    repository.delete_session(sid, db_path=db_path)
    assert repository.get_turns(sid, db_path=db_path) == []
    assert repository.get_feedback(session_id=sid, db_path=db_path) == []


def test_invalid_rating_rejected(db_path):
    with pytest.raises(ValueError):
        repository.rate_feedback(1, "amazing", db_path=db_path)


def test_sql_injection_text_is_stored_literally(db_path):
    sid = repository.create_session("free", "x'); DROP TABLE sessions;--", db_path=db_path)
    assert repository.get_session(sid, db_path=db_path)["scenario"].startswith("x');")


def test_vocabulary_persistence(db_path):
    wid = repository.save_word({"word": "Meanwhile", "definition": "at the same time",
                                "synonyms": ["simultaneously"]}, db_path=db_path)
    # Saving the same word with different case updates instead of duplicating
    wid2 = repository.save_word({"word": "meanwhile", "definition": "during this time"}, db_path=db_path)
    assert wid == wid2
    words = repository.list_words(db_path=db_path)
    assert len(words) == 1 and words[0]["definition"] == "during this time"
    repository.update_word(wid, notes="my note", mastered=True, db_path=db_path)
    repository.record_review(wid, correct=True, db_path=db_path)
    w = repository.list_words(db_path=db_path)[0]
    assert w["notes"] == "my note" and w["mastered"] == 1 and w["correct_count"] == 1
    assert repository.list_words(only_unmastered=True, db_path=db_path) == []
    repository.delete_word(wid, db_path=db_path)
    assert repository.list_words(db_path=db_path) == []


def test_preferences_and_delete_all(db_path):
    repository.set_preference("profile", {"goal": "interview"}, db_path=db_path)
    assert repository.get_preference("profile", db_path=db_path) == {"goal": "interview"}
    sid = repository.create_session("daily", "x", db_path=db_path)
    repository.add_turn(sid, "user", "hello there", db_path=db_path)
    repository.save_word({"word": "hello", "definition": "greeting"}, db_path=db_path)
    repository.delete_all_history(db_path=db_path)
    assert repository.list_sessions(db_path=db_path) == []
    assert len(repository.list_words(db_path=db_path)) == 1          # vocabulary kept by default
    repository.delete_all_history(include_vocabulary=True, db_path=db_path)
    assert repository.list_words(db_path=db_path) == []
    assert repository.get_preference("profile", db_path=db_path) == {"goal": "interview"}


def test_export_all(db_path):
    repository.create_session("daily", "x", db_path=db_path)
    data = repository.export_all(db_path=db_path)
    assert set(data) == {"sessions", "turns", "feedback", "vocabulary", "practice_attempts"}
    assert len(data["sessions"]) == 1
