"""Learning-profile form (used by the Dashboard on first launch and by Settings)."""

import streamlit as st

from config.settings import ENGLISH_VARIETIES, FEEDBACK_FREQUENCIES
from core.learning_engine import DAILY_MINUTES, FOCUS_AREAS, GOALS, PROFICIENCY_LEVELS


def profile_form(profile: dict, submit_label: str) -> dict | None:
    """Profile form shared with the Settings page. Returns the new profile when submitted."""
    with st.form("profile_form"):
        c1, c2 = st.columns(2)
        proficiency = c1.selectbox("Your current English level", PROFICIENCY_LEVELS,
                                   index=PROFICIENCY_LEVELS.index(profile["proficiency"]),
                                   help="Your own estimate. LinguaAI does not judge your level from one sentence.")
        goal = c2.selectbox("Main goal", list(GOALS), format_func=GOALS.get,
                            index=list(GOALS).index(profile["goal"]) if profile["goal"] in GOALS else 0)
        minutes = c1.select_slider("Daily practice time (minutes)", DAILY_MINUTES,
                                   value=profile["daily_minutes"] if profile["daily_minutes"] in DAILY_MINUTES else 10)
        variety = c2.radio("Preferred English", ENGLISH_VARIETIES, horizontal=True,
                           index=ENGLISH_VARIETIES.index(profile["variety"]) if profile["variety"] in ENGLISH_VARIETIES else 0)
        focus = st.multiselect("Areas you want to improve", FOCUS_AREAS,
                               default=[f for f in profile["focus_areas"] if f in FOCUS_AREAS])
        freq = st.radio("When should I give grammar feedback?", list(FEEDBACK_FREQUENCIES),
                        format_func=FEEDBACK_FREQUENCIES.get, horizontal=True,
                        index=list(FEEDBACK_FREQUENCIES).index(profile["feedback_frequency"]))
        if st.form_submit_button(submit_label, type="primary"):
            return {"proficiency": proficiency, "goal": goal, "daily_minutes": minutes, "variety": variety,
                    "focus_areas": focus, "feedback_frequency": freq, "completed_onboarding": True}
    return None
