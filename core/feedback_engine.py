"""
Decides *when* to give feedback, and builds end-of-session feedback.

Feedback frequency (chosen in your profile):
* every_turn      - check each answer right after you speak
* every_3_turns   - check the last 3 answers together, every 3 answers
* end_of_session  - check everything when you end the session
* on_request      - only when you press "Check my last answer"

This keeps the conversation from feeling like a constant exam.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from statistics import mean

from config.prompts import MODES, SESSION_FEEDBACK_SYSTEM_PROMPT, SESSION_FEEDBACK_USER_TEMPLATE
from core.llm_client import LLMError, OllamaClient
from utils.validators import as_str, as_str_list, extract_json_object

logger = logging.getLogger(__name__)

BATCH_SIZE = 3


def turns_due_for_feedback(frequency: str, user_turn_count: int, checked_count: int,
                           session_ending: bool = False) -> int:
    """How many of the latest unchecked user turns should be checked now.

    ``user_turn_count``: user answers so far; ``checked_count``: answers already checked.
    """
    pending = max(user_turn_count - checked_count, 0)
    if pending == 0:
        return 0
    if frequency == "every_turn":
        return pending
    if frequency == "every_3_turns":
        if pending >= BATCH_SIZE or session_ending:
            return pending
        return 0
    if frequency == "end_of_session":
        return pending if session_ending else 0
    return 0  # on_request: only when the user asks


@dataclass
class SessionStats:
    """Measured statistics for a session (computed, never invented)."""
    user_turns: int = 0
    voice_turns: int = 0
    total_words: int = 0
    speaking_seconds: float = 0.0
    avg_wpm: float | None = None
    filler_count: int = 0
    fillers_per_100_words: float | None = None
    long_pauses: int = 0
    avg_answer_words: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def describe(self) -> str:
        lines = [f"- Answers: {self.user_turns} ({self.voice_turns} spoken)",
                 f"- Total words: {self.total_words}"]
        if self.avg_answer_words is not None:
            lines.append(f"- Average answer length: {self.avg_answer_words} words")
        if self.voice_turns:
            lines.append(f"- Speaking time: {self.speaking_seconds:.0f} s")
            lines.append(f"- Average speaking rate: {self.avg_wpm} words/min" if self.avg_wpm
                         else "- Speaking rate: not enough speech to measure")
            lines.append(f"- Filler words detected (minimum): {self.filler_count}")
            lines.append(f"- Pauses longer than threshold: {self.long_pauses}")
        return "\n".join(lines)


def compute_session_stats(user_metrics: list[dict], input_types: list[str]) -> SessionStats:
    stats = SessionStats(user_turns=len(user_metrics))
    stats.voice_turns = sum(1 for t in input_types if t == "voice")
    words = [m.get("word_count") or 0 for m in user_metrics]
    stats.total_words = sum(words)
    if words:
        stats.avg_answer_words = round(mean(words), 1)
    voice = [m for m, t in zip(user_metrics, input_types) if t == "voice"]
    stats.speaking_seconds = round(sum(m.get("speaking_seconds") or 0 for m in voice), 1)
    stats.filler_count = sum(m.get("filler_count") or 0 for m in voice)
    stats.long_pauses = sum(m.get("long_pauses") or 0 for m in voice)
    voice_words = sum(m.get("word_count") or 0 for m in voice)
    if stats.speaking_seconds >= 5 and voice_words:
        stats.avg_wpm = round(voice_words / stats.speaking_seconds * 60, 1)
    if voice_words >= 20:
        stats.fillers_per_100_words = round(stats.filler_count / voice_words * 100, 1)
    return stats


@dataclass
class SessionFeedback:
    ok: bool = True
    summary: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    clarity: str = ""
    grammar: str = ""
    relevance: str = ""
    structure: str = ""
    vocabulary: str = ""
    next_steps: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def parse_session_feedback(raw: str | None, stats: SessionStats) -> SessionFeedback:
    data = extract_json_object(raw)
    if data is None:
        return SessionFeedback(ok=False, stats=stats.to_dict(),
                               error="The AI's session feedback could not be read. Your measured "
                                     "statistics are still shown below.")
    return SessionFeedback(
        ok=True,
        summary=as_str(data.get("summary")),
        strengths=as_str_list(data.get("strengths")),
        improvements=as_str_list(data.get("improvements")),
        clarity=as_str(data.get("clarity")),
        grammar=as_str(data.get("grammar")),
        relevance=as_str(data.get("relevance")),
        structure=as_str(data.get("structure")),
        vocabulary=as_str(data.get("vocabulary")),
        next_steps=as_str_list(data.get("next_steps")),
        stats=stats.to_dict(),
    )


def generate_session_feedback(client: OllamaClient, *, mode: str, scenario: str, proficiency: str,
                              transcript: str, stats: SessionStats) -> SessionFeedback:
    if stats.user_turns == 0:
        return SessionFeedback(ok=False, stats=stats.to_dict(),
                               error="You haven't said anything yet, so there is nothing to review.")
    messages = [
        {"role": "system", "content": SESSION_FEEDBACK_SYSTEM_PROMPT.format(
            mode_label=MODES.get(mode, MODES["free"])["label"], scenario=scenario, proficiency=proficiency)},
        {"role": "user", "content": SESSION_FEEDBACK_USER_TEMPLATE.format(
            transcript=transcript, metrics=stats.describe())},
    ]
    try:
        raw = client.chat(messages, json_mode=True, max_tokens=700, temperature=0.3)
    except LLMError as exc:
        return SessionFeedback(ok=False, stats=stats.to_dict(), error=str(exc))
    return parse_session_feedback(raw, stats)
