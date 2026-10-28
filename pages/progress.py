"""Progress: charts built only from recorded data, plus export and deletion."""

import json
from collections import Counter

import pandas as pd
import streamlit as st

from config.prompts import GRAMMAR_CATEGORIES
from database import repository
from ui import components

st.title("Progress")
turns = repository.user_turn_metrics()

if not turns:
    components.empty_state("Nothing to show yet. Your progress appears here after your first practice session.")
else:
    df = pd.DataFrame(turns)
    df["date"] = pd.to_datetime(df["created_at"]).dt.date
    voice = df[df["input_type"] == "voice"]
    sessions = df["session_id"].nunique()

    c = st.columns(4)
    c[0].metric("Sessions", sessions)
    c[1].metric("Recorded speaking time", f"{(voice['speaking_seconds'].fillna(0).sum() / 60):.1f} min",
                help="Time actually speaking (pauses removed).")
    c[2].metric("Words", int(df["word_count"].fillna(0).sum()))
    measured = voice[voice["words_per_minute"].notna()]
    c[3].metric("Average speaking rate", f"{measured['words_per_minute'].mean():.0f} wpm" if len(measured) else "-",
                help="Only answers with at least 3 s of speech are included.")

    st.subheader("Activity per day")
    daily = df.groupby("date").agg(answers=("id", "count"), words=("word_count", "sum"))
    st.bar_chart(daily[["words"]], y_label="Words", x_label="Date")

    st.subheader("Speaking trends")
    if voice["date"].nunique() < 2 or len(measured) < 3:
        st.caption("Trends appear after you have spoken on at least 2 different days (3+ measured answers).")
    else:
        vday = voice.groupby("date").agg(wpm=("words_per_minute", "mean"), words=("word_count", "sum"),
                                         fillers=("filler_count", "sum"))
        vday["fillers per 100 words"] = (vday["fillers"] / vday["words"].where(vday["words"] > 0) * 100).round(1)
        col1, col2 = st.columns(2)
        col1.markdown("**Words per minute**")
        col1.line_chart(vday[["wpm"]].dropna())
        col2.markdown("**Filler words per 100 words** (minimum count)")
        col2.line_chart(vday[["fillers per 100 words"]].dropna())

    st.subheader("Feedback categories")
    cats: Counter = Counter()
    for fb in repository.get_feedback(kind="grammar"):
        if fb["user_rating"] in ("wrong", "dismissed"):
            continue
        for issue in fb["payload"].get("issues", []) or []:
            if isinstance(issue, dict) and issue.get("category") not in (None, "informal_ok"):
                cats[GRAMMAR_CATEGORIES.get(issue["category"], issue["category"])] += 1
    if cats:
        st.bar_chart(pd.DataFrame({"count": cats}).sort_values("count", ascending=False), horizontal=True)
        st.caption("Feedback you marked as 'wrong' or 'dismissed' is excluded.")
    else:
        st.caption("No grammar feedback recorded yet.")

    fillers: Counter = Counter()
    for raw in voice["metrics_json"].dropna():
        try:
            fillers.update(json.loads(raw).get("fillers", {}))
        except ValueError:
            continue
    st.subheader("Most frequent filler words")
    if fillers:
        st.bar_chart(pd.DataFrame({"count": fillers}).sort_values("count", ascending=False))
    else:
        st.caption("No filler words detected so far (note: speech recognition may miss some).")

    st.subheader("Interview practice")
    interviews = df[df["mode"] == "interview"].groupby("session_id").agg(
        date=("date", "first"), scenario=("scenario", "first"), answers=("id", "count"),
        avg_words=("word_count", "mean"))
    if len(interviews):
        st.dataframe(interviews.round(1), hide_index=True)
    else:
        st.caption("No interview sessions yet.")

# ---------------------------------------------------------------- export/delete
st.divider()
st.subheader("Your data")
c1, c2, c3 = st.columns(3)
if turns:
    export_cols = ["created_at", "mode", "scenario", "input_type", "word_count", "speaking_seconds",
                   "words_per_minute", "filler_count", "long_pauses"]
    c1.download_button("Export answers (CSV)", pd.DataFrame(turns)[export_cols].to_csv(index=False),
                       file_name="linguaai_progress.csv", mime="text/csv", icon=":material/download:")
c2.download_button("Export everything (JSON)", json.dumps(repository.export_all(), indent=2, default=str),
                   file_name="linguaai_export.json", mime="application/json", icon=":material/download:")
with c3.popover("Delete all history", icon=":material/delete_forever:"):
    st.write("Deletes all sessions, messages, feedback and practice attempts. This cannot be undone.")
    also_vocab = st.checkbox("Also delete my saved vocabulary")
    confirm = st.text_input("Type DELETE to confirm")
    if st.button("Delete", type="primary", disabled=confirm != "DELETE"):
        repository.delete_all_history(include_vocabulary=also_vocab)
        st.toast("History deleted.")
        st.rerun()
