"""Conversation engine with a fake language model (no Ollama needed)."""

import pytest

from core.conversation_engine import ConversationEngine
from core.llm_client import LLMError, ModelNotInstalledError
from database import repository


def make_engine(llm, db_path, **kw):
    return ConversationEngine(llm, mode="daily", scenario="Hobbies", proficiency="Beginner",
                              variety="British", db_path=db_path, **kw)


def test_full_turn_is_saved(fake_llm, db_path):
    llm = fake_llm(["That sounds fun! How often do you play?"])
    engine = make_engine(llm, db_path)
    engine.start()
    engine.add_user_message("I play football", metrics={"word_count": 3})
    reply = engine.generate_reply()
    assert reply.text.startswith("That sounds fun")
    turns = repository.get_turns(engine.session_id, db_path=db_path)
    assert [t["role"] for t in turns] == ["assistant", "user", "assistant"]
    system = llm.calls[0]["messages"][0]
    assert system["role"] == "system" and "British" in system["content"] and "Hobbies" in system["content"]


def test_context_is_trimmed(fake_llm, db_path):
    llm = fake_llm(["ok"] * 20)
    engine = make_engine(llm, db_path, context_turns=4)
    engine.start()
    for i in range(6):
        engine.add_user_message(f"message {i}")
        engine.generate_reply()
    sent = llm.calls[-1]["messages"]
    assert len(sent) == 1 + 4                       # system + last 4 messages
    assert sent[-1]["content"] == "message 5"


def test_empty_message_rejected(fake_llm, db_path):
    engine = make_engine(fake_llm(), db_path)
    engine.start()
    with pytest.raises(ValueError):
        engine.add_user_message("   ")


def test_reply_requires_user_message(fake_llm, db_path):
    engine = make_engine(fake_llm(), db_path)
    engine.start()
    with pytest.raises(ValueError):
        engine.generate_reply()


def test_missing_model_error_propagates(fake_llm, db_path):
    engine = make_engine(fake_llm(error=ModelNotInstalledError("ollama pull llama3.2:3b")), db_path)
    engine.start()
    engine.add_user_message("hello")
    with pytest.raises(LLMError):
        engine.generate_reply()


def test_empty_reply_is_an_error(fake_llm, db_path):
    engine = make_engine(fake_llm(["   "]), db_path)
    engine.start()
    engine.add_user_message("hello")
    with pytest.raises(LLMError):
        engine.generate_reply()


def test_history_off_saves_nothing(fake_llm, db_path):
    engine = make_engine(fake_llm(["hi"]), db_path, save_history=False)
    engine.start()
    engine.add_user_message("hello")
    engine.generate_reply()
    engine.end()
    assert engine.session_id is None
    assert repository.list_sessions(db_path=db_path) == []


def test_unknown_mode_rejected(fake_llm):
    with pytest.raises(ValueError):
        ConversationEngine(fake_llm(), mode="karaoke", scenario="x")


def test_previous_assistant_text(fake_llm, db_path):
    engine = make_engine(fake_llm(["Next question?"]), db_path)
    opening = engine.start()
    msg = engine.add_user_message("answer")
    assert engine.previous_assistant_text(msg) == opening.text
