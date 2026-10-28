"""Fluency metric calculations."""

from core.fluency_analyzer import analyze_fluency, count_fillers, find_repeated_words, merged_speech_time
from core.speech_recognition import WordTiming


def words_at(spec):
    """spec: list of (word, start, end)."""
    return [WordTiming(w, s, e, 0.9) for w, s, e in spec]


def test_empty_transcript():
    m = analyze_fluency("", [], 2.0)
    assert m.word_count == 0 and m.words_per_minute is None and m.speaking_seconds == 0


def test_speaking_time_excludes_long_silence():
    words = words_at([("hello", 0.0, 0.5), ("there", 0.6, 1.0), ("friend", 5.0, 5.5)])
    # 0.0-1.0 (gap 0.1 merged) + 5.0-5.5 = 1.5 s, the 4 s silence is excluded
    assert abs(merged_speech_time(words) - 1.5) < 1e-9


def test_wpm_uses_speaking_time_not_recording_time():
    words = words_at([(f"w{i}", i * 0.4, i * 0.4 + 0.35) for i in range(20)])  # ~8 s of speech
    m = analyze_fluency(" ".join(f"w{i}" for i in range(20)), words, recording_seconds=30.0)
    assert m.recording_seconds == 30.0
    assert 7.5 < m.speaking_seconds < 8.0
    assert 140 < m.words_per_minute < 165


def test_wpm_not_reported_for_short_answers():
    words = words_at([("yes", 0.0, 0.4)])
    assert analyze_fluency("yes", words, 1.0).words_per_minute is None


def test_fillers_counted_but_not_like():
    counts = count_fillers("Um, I like, uh, think you know it's umm fine. Like really.")
    assert counts["um"] == 2 and counts["uh"] == 1 and counts["you know"] == 1
    assert "like" not in counts


def test_long_pauses():
    words = words_at([("a", 0, 0.3), ("b", 0.4, 0.7), ("c", 2.5, 2.8), ("d", 2.9, 3.2)])
    m = analyze_fluency("a b c d", words, 4.0, long_pause_seconds=1.0)
    assert m.long_pauses == 1 and abs(m.longest_pause - 1.8) < 1e-6


def test_repeated_words_ignore_intensifiers():
    assert find_repeated_words("I I think it is very very good good") == ["i", "good"]


def test_sentence_stats_and_continuity():
    words = words_at([("I", 0, 0.2), ("went", 0.25, 0.5), ("home", 2.0, 2.4)])
    m = analyze_fluency("I went home. It was late!", words, 3.0)
    assert m.sentence_count == 2
    assert m.continuity is not None and 0 < m.continuity < 1
