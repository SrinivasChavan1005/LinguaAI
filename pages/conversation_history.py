"""Conversation History: browse, export and delete past sessions."""

import json

import streamlit as st

from config.prompts import MODES
from core.grammar_analyzer import GrammarFeedback
from database import repository
from ui import components

st.title("Conversation History")
sessions = [s for s in repository.list_sessions() if s["user_turns"]]
if not sessions:
    components.empty_state("No saved conversations yet. (If 'Save history' is off in Settings, "
                           "sessions are not stored.)")
    st.stop()

modes = sorted({s["mode"] for s in sessions})
mode_filter = st.multiselect("Filter by type", modes, format_func=lambda m: MODES.get(m, {}).get("label", m))
shown = [s for s in sessions if not mode_filter or s["mode"] in mode_filter]


def label(s: dict) -> str:
    return (f"{s['started_at']} · {MODES.get(s['mode'], {}).get('label', s['mode'])} · {s['scenario']} "
            f"· {s['user_turns']} answers")


choice = st.selectbox("Session", shown, format_func=label)
if choice:
    turns = repository.get_turns(choice["id"])
    feedback = repository.get_feedback(session_id=choice["id"])
    by_turn = {f["turn_id"]: f for f in feedback if f["kind"] == "grammar"}
    session_fb = [f for f in feedback if f["kind"] == "session"]

    for t in turns:
        with st.chat_message(t["role"], avatar=":material/person:" if t["role"] == "user" else ":material/school:"):
            st.markdown(t["text"])
            if t["role"] == "user" and t["id"] in by_turn:
                f = by_turn[t["id"]]
                fb = GrammarFeedback.from_dict(f["payload"])
                rating = f" · you marked it **{f['user_rating']}**" if f["user_rating"] else ""
                with st.expander(f"Feedback{rating}"):
                    components.render_grammar_feedback(fb, f["id"], key=f"hist_{f['id']}")
    if session_fb:
        st.subheader("Session feedback")
        components.render_session_feedback(session_fb[0]["payload"])

    st.divider()
    c1, c2 = st.columns(2)
    export = {"session": choice, "turns": turns, "feedback": [{k: v for k, v in f.items() if k != "payload_json"}
                                                             for f in feedback]}
    c1.download_button("Export this session (JSON)", json.dumps(export, indent=2, default=str),
                       file_name=f"linguaai_session_{choice['id']}.json", mime="application/json",
                       icon=":material/download:")
    with c2.popover("Delete this session", icon=":material/delete:"):
        st.write("This permanently deletes the session, its messages and feedback.")
        if st.button("Yes, delete it", type="primary"):
            repository.delete_session(choice["id"])
            st.toast("Session deleted.")
            st.rerun()
