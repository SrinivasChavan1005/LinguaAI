"""Grammar feedback parsing, including malformed model output."""

import json

from core.grammar_analyzer import GrammarAnalyzer, GrammarFeedback, parse_grammar_response
from core.llm_client import OllamaNotRunningError

ORIGINAL = "Yesterday I am going to college and I meet my friend."

GOOD = {
    "has_issues": True,
    "corrected": "Yesterday, I went to college and met my friend.",
    "issues": [{"category": "grammar", "original": "am going", "suggestion": "went",
                "explanation": "The sentence is about the past, so use the past tense."}],
    "alternatives": ["I went to college yesterday and ran into my friend."],
    "practice": "What did you do yesterday?",
    "repeat_after_me": "Yesterday, I went to college and met my friend.",
}


def test_valid_json_is_parsed():
    fb = parse_grammar_response(ORIGINAL, json.dumps(GOOD))
    assert fb.ok and fb.has_issues
    assert fb.corrected.startswith("Yesterday, I went")
    assert fb.issues[0].category == "grammar"
    assert fb.practice == "What did you do yesterday?"


def test_json_inside_code_fence_and_prose():
    raw = "Sure! Here is the feedback:\n```json\n" + json.dumps(GOOD) + "\n```\nHope it helps."
    fb = parse_grammar_response(ORIGINAL, raw)
    assert fb.ok and fb.issues


def test_not_json_does_not_crash():
    fb = parse_grammar_response(ORIGINAL, "I think the sentence has a tense problem.")
    assert not fb.ok
    assert fb.error


def test_empty_and_none_output():
    assert not parse_grammar_response(ORIGINAL, "").ok
    assert not parse_grammar_response(ORIGINAL, None).ok


def test_truncated_json():
    raw = json.dumps(GOOD)[:60]
    assert not parse_grammar_response(ORIGINAL, raw).ok


def test_wrong_types_are_sanitised():
    raw = json.dumps({"has_issues": "yes", "corrected": ["not", "a", "string"], "issues": "oops",
                      "alternatives": "one alternative", "practice": 42, "repeat_after_me": None})
    fb = parse_grammar_response(ORIGINAL, raw)
    assert fb.ok
    assert fb.corrected == ORIGINAL          # list replaced by original
    assert fb.issues == []
    assert fb.alternatives == ["one alternative"]
    assert fb.practice == "42"


def test_unknown_category_is_normalised():
    data = dict(GOOD, issues=[{"category": "Verb Tense", "original": "am", "suggestion": "was",
                               "explanation": "past"}])
    fb = parse_grammar_response(ORIGINAL, json.dumps(data))
    assert fb.issues[0].category == "grammar"


def test_informal_only_is_not_counted_as_mistake():
    data = {"has_issues": True, "corrected": "Gonna grab lunch.",
            "issues": [{"category": "informal_ok", "original": "gonna", "suggestion": "going to",
                        "explanation": "Fine in casual speech."}]}
    fb = parse_grammar_response("Gonna grab lunch.", json.dumps(data))
    assert fb.ok and not fb.has_issues
    assert fb.real_error_categories == []


def test_roundtrip_dict():
    fb = parse_grammar_response(ORIGINAL, json.dumps(GOOD))
    again = GrammarFeedback.from_dict(json.loads(json.dumps(fb.to_dict())))
    assert again == fb


def test_analyzer_uses_json_mode(fake_llm):
    llm = fake_llm([json.dumps(GOOD)])
    fb = GrammarAnalyzer(llm, "British", "Beginner").analyze(ORIGINAL, context="What did you do?")
    assert fb.ok and llm.calls[0]["json_mode"] is True
    assert "British" in llm.calls[0]["messages"][0]["content"]


def test_analyzer_empty_transcript(fake_llm):
    llm = fake_llm()
    fb = GrammarAnalyzer(llm).analyze("   ")
    assert not fb.ok and llm.calls == []


def test_analyzer_handles_llm_error(fake_llm):
    llm = fake_llm(error=OllamaNotRunningError("Ollama is not running."))
    fb = GrammarAnalyzer(llm).analyze("I has a cat.")
    assert not fb.ok and "Ollama" in fb.error
