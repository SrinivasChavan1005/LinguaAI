"""Interview Practice: the AI plays the interviewer; feedback at the end."""

import streamlit as st

from database import repository
from ui import components
from ui.conversation_view import ConversationView

st.title("Interview Practice")
st.caption("The AI acts as a job interviewer. Feedback focuses on communication - clarity, grammar, "
           "relevance and structure - not on whether your technical answers are correct.")

tab_practice, tab_history = st.tabs(["Practice", "Past interviews"])
with tab_practice:
    with st.expander("Tips for structured answers", icon=":material/lightbulb:"):
        st.markdown(
            "- **STAR** for behavioural questions: *Situation, Task, Action, Result*.\n"
            "- **Present - Past - Future** for 'Tell me about yourself'.\n"
            "- Keep most answers to 45-90 seconds. Give one concrete example.")
    ConversationView("interview", ["interview"]).render()

with tab_history:
    sessions = [s for s in repository.list_sessions() if s["mode"] == "interview"]
    if not sessions:
        components.empty_state("No interview sessions yet. Finish an interview to see it here.")
    for s in sessions[:20]:
        fbs = repository.get_feedback(session_id=s["id"], kind="session")
        with st.expander(f"{s['started_at']} · {s['scenario']} · {s['user_turns']} answers"):
            if fbs:
                components.render_session_feedback(fbs[0]["payload"])
            else:
                st.caption("No session feedback was generated for this interview.")
