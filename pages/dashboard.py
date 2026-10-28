"""Dashboard: first-launch profile setup, today's plan and quick stats."""

import streamlit as st

from core.learning_engine import GOALS, build_daily_plan, build_recommendations
from database import repository
from ui import components, state
from ui.profile_form import profile_form

PAGE_FILES = {"voice": "pages/voice_practice.py", "interview": "pages/interview_practice.py",
              "pronunciation": "pages/pronunciation_lab.py", "vocabulary": "pages/vocabulary.py"}


profile = state.get_profile()

if not profile.get("completed_onboarding"):
    st.title("Welcome to LinguaAI")
    st.markdown("Your private, offline English communication coach. Let's set up your learning profile "
                "(you can change it any time in **Settings**).")
    new = profile_form(profile, "Save and continue")
    if new:
        state.save_profile(new)
        st.rerun()
    st.stop()

st.title("Dashboard")
st.caption(f"Goal: {GOALS.get(profile['goal'])} · {profile['daily_minutes']} min/day · "
           f"{profile['proficiency']} · {profile['variety']} English")

# ---------------------------------------------------------------- today's plan
st.subheader("Today's practice plan")
plan = build_daily_plan(profile)
cols = st.columns(len(plan))
for i, (col, item) in enumerate(zip(cols, plan)):
    with col.container(border=True):
        st.markdown(f"**{item.minutes} min** · {item.activity}")
        if st.button("Start", key=f"plan_{i}", icon=":material/play_arrow:"):
            if item.mode and item.page == "voice":
                st.session_state["voice_preset_mode"] = item.mode
            st.switch_page(PAGE_FILES[item.page])

# ------------------------------------------------------------------ quick stats
turns = repository.user_turn_metrics()
sessions = repository.list_sessions()
words = repository.list_words()
st.subheader("At a glance")
c = st.columns(4)
c[0].metric("Practice sessions", len([s for s in sessions if s["user_turns"]]))
c[1].metric("Answers given", len(turns))
c[2].metric("Words spoken/typed", sum(t["word_count"] or 0 for t in turns))
c[3].metric("Saved words", len(words))

# ------------------------------------------------------------- recommendations
st.subheader("Recommendations")
rec = build_recommendations(turns, repository.get_feedback(kind="grammar"), len(words))
if rec.note:
    st.caption(rec.note)
for item in rec.items:
    st.markdown(f"- {item}")

# ---------------------------------------------------------------- recent activity
st.subheader("Recent sessions")
recent = [s for s in sessions if s["user_turns"]][:5]
if not recent:
    components.empty_state("No sessions yet. Start with **Voice Practice** - it takes 2 minutes.")
else:
    st.dataframe(
        [{"Date": s["started_at"], "Mode": s["mode"], "Scenario": s["scenario"], "Answers": s["user_turns"],
          "Words": s["words"]} for s in recent],
        hide_index=True)
