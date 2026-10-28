"""Feedback timing policy, session statistics and session feedback parsing."""

import json

from core.feedback_engine import (compute_session_stats, generate_session_feedback, parse_session_feedback,
                                  turns_due_for_feedback)
from core.learning_engine import build_daily_plan, build_recommendations
from core.llm_client import LLMTimeoutError


def test_every_turn():
    assert turns_due_for_feedback("every_turn", 1, 0) == 1
    assert turns_due_for_feedback("every_turn", 3, 3) == 0


def test_every_three_turns():
    assert turns_due_for_feedback("every_3_turns", 2, 0) == 0
    assert turns_due_for_feedback("every_3_turns", 3, 0) == 3
    assert turns_due_for_feedback("every_3_turns", 2, 0, session_ending=True) == 2


def test_end_of_session_and_on_request():
    assert turns_due_for_feedback("end_of_session", 5, 0) == 0
    assert turns_due_for_feedback("end_of_session", 5, 0, session_ending=True) == 5
    assert turns_due_for_feedback("on_request", 5, 0, session_ending=True) == 0


def test_session_stats_only_use_voice_for_speech_metrics():
    metrics = [{"word_count": 30, "speaking_seconds": 12, "filler_count": 2, "long_pauses": 1},
               {"word_count": 10}]
    stats = compute_session_stats(metrics, ["voice", "text"])
    assert stats.user_turns == 2 and stats.voice_turns == 1 and stats.total_words == 40
    assert stats.avg_wpm == 150.0 and stats.filler_count == 2
    assert stats.fillers_per_100_words == round(2 / 30 * 100, 1)


def test_session_stats_empty():
    stats = compute_session_stats([], [])
    assert stats.user_turns == 0 and stats.avg_wpm is None


def test_session_feedback_parsing():
    stats = compute_session_stats([{"word_count": 5}], ["text"])
    good = parse_session_feedback(json.dumps({"summary": "Nice.", "strengths": ["clear"],
                                              "improvements": "use past tense"}), stats)
    assert good.ok and good.improvements == ["use past tense"] and good.stats["total_words"] == 5
    bad = parse_session_feedback("not json", stats)
    assert not bad.ok and bad.stats  # measured stats still available


def test_session_feedback_no_answers(fake_llm):
    llm = fake_llm()
    fb = generate_session_feedback(llm, mode="interview", scenario="HR questions", proficiency="Beginner",
                                   transcript="", stats=compute_session_stats([], []))
    assert not fb.ok and llm.calls == []


def test_session_feedback_llm_error(fake_llm):
    llm = fake_llm(error=LLMTimeoutError("took too long"))
    fb = generate_session_feedback(llm, mode="daily", scenario="x", proficiency="Beginner", transcript="hi",
                                   stats=compute_session_stats([{"word_count": 1}], ["text"]))
    assert not fb.ok and "too long" in fb.error


def test_daily_plan_uses_profile_time():
    plan = build_daily_plan({"daily_minutes": 15, "goal": "interview", "focus_areas": ["Pronunciation"]})
    assert sum(p.minutes for p in plan) == 15
    assert plan[0].page == "interview" and plan[1].page == "pronunciation"
    assert sum(p.minutes for p in build_daily_plan({"daily_minutes": 5})) == 5


def test_recommendations_preliminary_and_ignore_wrong_feedback():
    rec = build_recommendations([], [], 0)
    assert rec.preliminary and not rec.items
    turns = [{"input_type": "voice", "word_count": 4, "filler_count": 0}] * 3
    feedback = [{"user_rating": "wrong", "payload": {"issues": [{"category": "grammar"}]}}]
    rec = build_recommendations(turns, feedback, 10)
    assert rec.preliminary and "preliminary" in rec.note
    assert not any("Incorrect grammar" in i for i in rec.items)   # marked wrong -> ignored
    assert any("short" in i for i in rec.items)
