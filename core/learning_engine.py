"""
Personal learning plan and recommendations.

* The *plan* is built from your profile (goal, daily time, focus areas).
* *Recommendations* are built only from what has actually been recorded.
  With little history they are marked as preliminary - we never guess your
  level from a single sentence.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

PROFICIENCY_LEVELS = ("Beginner", "Elementary", "Intermediate", "Advanced")
GOALS = {
    "everyday": "Everyday conversation",
    "interview": "Interview communication",
    "professional": "Professional English",
    "presentation": "Presentation skills",
    "pronunciation": "Pronunciation practice",
    "grammar": "Grammar improvement",
    "vocabulary": "Vocabulary development",
}
FOCUS_AREAS = ("Grammar", "Vocabulary", "Pronunciation", "Fluency", "Confidence", "Listening")
DAILY_MINUTES = (5, 10, 15, 20, 30)
MIN_TURNS_FOR_RECOMMENDATIONS = 10

DEFAULT_PROFILE = {
    "proficiency": "Intermediate",
    "goal": "everyday",
    "daily_minutes": 10,
    "variety": "American",
    "focus_areas": ["Grammar", "Fluency"],
    "feedback_frequency": "every_turn",
    "completed_onboarding": False,
}

# Which activity to suggest for each goal (page, mode, label)
_GOAL_ACTIVITIES = {
    "everyday": [("voice", "daily", "Daily conversation")],
    "interview": [("interview", "interview", "Interview practice")],
    "professional": [("voice", "workplace", "Workplace conversation")],
    "presentation": [("voice", "presentation", "Presentation practice")],
    "pronunciation": [("pronunciation", None, "Pronunciation Lab")],
    "grammar": [("voice", "daily", "Conversation with grammar feedback")],
    "vocabulary": [("vocabulary", None, "Vocabulary revision")],
}


@dataclass
class PlanItem:
    minutes: int
    activity: str
    page: str            # "voice", "interview", "pronunciation", "vocabulary"
    mode: str | None = None


def build_daily_plan(profile: dict) -> list[PlanItem]:
    """Split the daily practice time into realistic blocks."""
    minutes = int(profile.get("daily_minutes", 10))
    if minutes not in DAILY_MINUTES:
        minutes = 10
    goal = profile.get("goal", "everyday")
    page, mode, label = _GOAL_ACTIVITIES.get(goal, _GOAL_ACTIVITIES["everyday"])[0]
    focus = profile.get("focus_areas", [])

    if minutes <= 5:
        return [PlanItem(5, label, page, mode)]
    plan = [PlanItem(round(minutes * 0.6), label, page, mode)]
    remaining = minutes - plan[0].minutes
    if "Pronunciation" in focus and page != "pronunciation":
        plan.append(PlanItem(remaining, "Pronunciation Lab: repeat 3 sentences", "pronunciation"))
    elif "Vocabulary" in focus and page != "vocabulary":
        plan.append(PlanItem(remaining, "Vocabulary revision", "vocabulary"))
    elif page != "voice":
        plan.append(PlanItem(remaining, "Free conversation", "voice", "free"))
    else:
        plan.append(PlanItem(remaining, "Vocabulary revision", "vocabulary"))
    return plan


@dataclass
class Recommendations:
    preliminary: bool
    items: list[str] = field(default_factory=list)
    note: str = ""


def build_recommendations(user_turns: list[dict], grammar_feedback: list[dict],
                          vocab_count: int) -> Recommendations:
    """Recommendations derived from recorded data only."""
    n = len(user_turns)
    rec = Recommendations(preliminary=n < MIN_TURNS_FOR_RECOMMENDATIONS)
    if n == 0:
        rec.note = "No practice recorded yet. Complete a session and recommendations will appear here."
        return rec
    if rec.preliminary:
        rec.note = (f"Based on only {n} answer(s) so far - these suggestions are preliminary. "
                    f"They become more reliable after {MIN_TURNS_FOR_RECOMMENDATIONS} answers.")

    # Grammar categories (ignore feedback the user marked as wrong/dismissed)
    cats: Counter[str] = Counter()
    for fb in grammar_feedback:
        if fb.get("user_rating") in ("wrong", "dismissed"):
            continue
        for issue in fb.get("payload", {}).get("issues", []) or []:
            cat = issue.get("category") if isinstance(issue, dict) else None
            if cat and cat != "informal_ok":
                cats[cat] += 1
    if cats:
        from config.prompts import GRAMMAR_CATEGORIES

        top, count = cats.most_common(1)[0]
        rec.items.append(f"Your most frequent feedback type is '{GRAMMAR_CATEGORIES.get(top, top)}' "
                         f"({count} times). Review those corrections in Conversation History.")

    voice = [t for t in user_turns if t.get("input_type") == "voice"]
    words = sum(t.get("word_count") or 0 for t in voice)
    fillers = sum(t.get("filler_count") or 0 for t in voice)
    if words >= 50 and fillers / words > 0.05:
        rec.items.append(f"About {fillers / words * 100:.0f} filler words per 100 words were detected. "
                         "Try pausing silently instead of saying 'um'.")
    answer_lengths = [t.get("word_count") or 0 for t in user_turns]
    if answer_lengths and sum(answer_lengths) / len(answer_lengths) < 8:
        rec.items.append("Your answers are often short. Try adding a reason or an example "
                         "('...because...', 'For example, ...').")
    if not voice:
        rec.items.append("You have only typed so far. Try speaking to practise fluency and pronunciation.")
    if vocab_count < 5:
        rec.items.append("Save useful words to your Vocabulary list so you can revise them.")
    if not rec.items:
        rec.items.append("Keep going! Try a new scenario to stretch your vocabulary.")
    return rec
