"""
LinguaAI - Offline Communication Coach.

Start with:  run_linguaai.bat   (or:  python -m streamlit run app.py)

This file sets up logging, the database and navigation; each page lives in
``pages/``. Everything runs locally: see docs/PRIVACY.md.
"""

from __future__ import annotations

import os
import time

# Make absolutely sure no model library tries to download anything while the
# app is running. Models are prepared once by scripts/download_models.py.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import streamlit as st  # noqa: E402

from database.database import DatabaseError, initialize  # noqa: E402
from ui import components, state  # noqa: E402
from utils.logging_config import setup_logging  # noqa: E402

_started = time.perf_counter()
st.set_page_config(page_title="LinguaAI - Offline Communication Coach", page_icon=":material/record_voice_over:",
                   layout="wide")
setup_logging()


@st.cache_resource(show_spinner=False)
def _init_database() -> int:
    return initialize()


try:
    _init_database()
except DatabaseError as exc:
    st.error(f"**Database problem:** {exc}", icon=":material/database:")
    st.stop()

components.inject_css()
settings = state.get_settings()

pages = {
    "Practice": [
        st.Page("pages/dashboard.py", title="Dashboard", icon=":material/home:", default=True),
        st.Page("pages/voice_practice.py", title="Voice Practice", icon=":material/mic:"),
        st.Page("pages/interview_practice.py", title="Interview Practice", icon=":material/work:"),
        st.Page("pages/pronunciation_lab.py", title="Pronunciation Lab", icon=":material/graphic_eq:"),
        st.Page("pages/vocabulary.py", title="Vocabulary", icon=":material/menu_book:"),
    ],
    "Your data": [
        st.Page("pages/conversation_history.py", title="Conversation History", icon=":material/history:"),
        st.Page("pages/progress.py", title="Progress", icon=":material/insights:"),
        st.Page("pages/settings.py", title="Settings", icon=":material/settings:"),
    ],
}
nav = st.navigation(pages)

with st.sidebar:
    st.markdown("### LinguaAI")
    st.caption("Offline Communication Coach")
components.sidebar_status(settings)
if settings.load_warnings:
    st.sidebar.warning("Some settings were invalid and reset to defaults. See Settings.")

monitor = state.get_monitor()
if monitor.startup_seconds is None:
    monitor.startup_seconds = round(time.perf_counter() - _started, 2)

nav.run()
