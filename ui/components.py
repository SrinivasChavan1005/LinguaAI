"""Reusable UI pieces (status panel, feedback cards, metric displays)."""

from __future__ import annotations

import streamlit as st

from config.prompts import GRAMMAR_CATEGORIES
from config.settings import AppSettings
from core.fluency_analyzer import describe_wpm
from core.grammar_analyzer import GrammarFeedback
from core.speech_recognition import whisper_model_available
from core.speech_synthesis import piper_voice_available, windows_tts_supported
from database import repository
from ui import state

CSS = """
<style>
:root { --la-accent: #0f766e; --la-soft: rgba(15,118,110,.08); --la-warn: #b45309; }
.block-container { padding-top: 2.2rem; max-width: 1100px; }
.la-offline { display:flex; gap:.5rem; align-items:center; padding:.55rem .75rem; border-radius:.6rem;
  background: var(--la-soft); border:1px solid rgba(15,118,110,.25); font-size:.86rem; }
.la-dot { width:.55rem; height:.55rem; border-radius:50%; display:inline-block; flex-shrink:0; }
.la-status { font-size:.82rem; line-height:1.7; }
.la-pill { display:inline-block; padding:.05rem .5rem; border-radius:999px; font-size:.75rem;
  border:1px solid rgba(128,128,128,.35); margin-right:.3rem; }
.la-cat-grammar { border-color:#dc2626; color:#dc2626; }
.la-cat-word_choice, .la-cat-awkward, .la-cat-unnatural { border-color:#b45309; color:#b45309; }
.la-cat-inappropriate { border-color:#7c3aed; color:#7c3aed; }
.la-cat-informal_ok { border-color:#15803d; color:#15803d; }
.la-muted { opacity:.7; font-size:.85rem; }
.la-word { display:inline-block; padding:.1rem .45rem; margin:.15rem; border-radius:.4rem; font-size:1rem; }
.la-w-match { background: rgba(21,128,61,.12); }
.la-w-unsure { background: rgba(180,83,9,.15); }
.la-w-missing { background: rgba(220,38,38,.15); text-decoration: line-through; }
.la-w-different { background: rgba(220,38,38,.15); }
.la-w-extra { background: rgba(100,116,139,.15); font-style: italic; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _dot(ok: bool | None) -> str:
    color = "#16a34a" if ok else ("#d97706" if ok is None else "#dc2626")
    return f'<span class="la-dot" style="background:{color}"></span>'


def sidebar_status(settings: AppSettings) -> None:
    """Offline indicator + readiness of each local component."""
    st.sidebar.markdown(
        f'<div class="la-offline">{_dot(True)}<div><b>Offline mode</b><br>'
        '<span class="la-muted">Speech, AI and voice all run on this computer. '
        'No data is sent to the internet.</span></div></div>', unsafe_allow_html=True)
    status = state.ollama_status(settings.ollama_host, settings.ollama_model)
    whisper_ok = whisper_model_available(settings.whisper_model)
    if settings.tts_engine == "piper":
        voice_ok, voice_label = piper_voice_available(settings.piper_voice), f"Voice: {settings.piper_voice}"
    else:
        voice_ok, voice_label = windows_tts_supported(), "Voice: Windows built-in"
    llm_ok = status.running and status.model_ready
    lines = [
        f"{_dot(whisper_ok)} Speech recognition: {settings.whisper_model}",
        f"{_dot(llm_ok if status.running else False)} AI model: {settings.ollama_model}"
        + ("" if status.running else " (Ollama not running)"),
        f"{_dot(voice_ok)} {voice_label}",
    ]
    st.sidebar.markdown('<div class="la-status">' + "<br>".join(lines) + "</div>", unsafe_allow_html=True)


def readiness_messages(settings: AppSettings) -> tuple[list[str], list[str]]:
    """Returns (blocking_errors, warnings) for starting a conversation."""
    errors, warnings = [], []
    status = state.ollama_status(settings.ollama_host, settings.ollama_model)
    if not status.running:
        errors.append(f"**AI model unavailable:** {status.message}")
    elif not status.model_ready:
        errors.append(f"**AI model missing:** {status.message}")
    if not whisper_model_available(settings.whisper_model):
        warnings.append(f"Speech recognition model '{settings.whisper_model}' is not downloaded, so "
                        "you can only type. Run `setup_linguaai.bat` to download it.")
    if settings.tts_engine == "piper" and not piper_voice_available(settings.piper_voice):
        warnings.append(f"Piper voice '{settings.piper_voice}' is not downloaded, so replies will not be "
                        "spoken. Run `setup_linguaai.bat`, or choose the Windows voice in Settings.")
    return errors, warnings


def render_fluency(metrics: dict) -> None:
    """Compact fluency metrics for one spoken answer."""
    if not metrics:
        return
    cols = st.columns(4)
    cols[0].metric("Speaking time", f"{metrics.get('speaking_seconds', 0):.1f}s",
                   help="Time spent speaking (pauses of 0.3 s or more removed). "
                        f"Total recording: {metrics.get('recording_seconds', 0):.1f}s")
    wpm = metrics.get("words_per_minute")
    cols[1].metric("Words / min", f"{wpm:.0f}" if wpm else "-", help=describe_wpm(wpm))
    cols[2].metric("Filler words", metrics.get("filler_count", 0),
                   help="Minimum count: speech recognition may drop some 'um'/'uh'.")
    cols[3].metric("Long pauses", metrics.get("long_pauses", 0),
                   help="Pauses are normal; this is information, not an error count.")
    extras = []
    if metrics.get("fillers"):
        extras.append("Fillers: " + ", ".join(f"{k} x{v}" for k, v in metrics["fillers"].items()))
    if metrics.get("repeated_words"):
        extras.append("Repeated: " + ", ".join(metrics["repeated_words"]))
    for w in metrics.get("audio_warnings", []):
        extras.append("Audio: " + w)
    if extras:
        st.caption(" · ".join(extras))


def render_grammar_feedback(fb: GrammarFeedback, feedback_id: int | None, key: str,
                            on_hear=None, on_practise=None) -> None:
    """Show grammar feedback with rating buttons."""
    if not fb.ok:
        st.warning(fb.error or "Feedback is not available for this answer.")
        return
    if not fb.has_issues:
        st.success("Looks good - no mistakes found." + (f" {fb.error}" if fb.error else ""))
        informal = [i for i in fb.issues if i.category == "informal_ok"]
        for issue in informal:
            st.caption(f"Informal but acceptable: '{issue.original}' - {issue.explanation}")
    else:
        st.markdown(f"**You said:** {fb.original}")
        st.markdown(f"**Suggested:** {fb.corrected}")
        for issue in fb.issues:
            label = GRAMMAR_CATEGORIES.get(issue.category, "Other")
            st.markdown(
                f'<span class="la-pill la-cat-{issue.category}">{label}</span> '
                f"<b>{_esc(issue.original)}</b> &rarr; <b>{_esc(issue.suggestion)}</b><br>"
                f'<span class="la-muted">{_esc(issue.explanation)}</span>', unsafe_allow_html=True)
    if fb.alternatives:
        st.markdown("**Other natural ways to say it:**\n" + "\n".join(f"- {a}" for a in fb.alternatives))
    if fb.practice:
        st.markdown(f"**Practice question:** {fb.practice}")
    if fb.repeat_after_me:
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.markdown(f"**Repeat after me:** _{fb.repeat_after_me}_")
        if on_hear and c2.button("Hear it", key=f"{key}_hear", icon=":material/volume_up:"):
            on_hear(fb.repeat_after_me)
        if on_practise and c3.button("Practise", key=f"{key}_prac", icon=":material/record_voice_over:"):
            on_practise(fb.repeat_after_me)
    st.caption("AI suggestions can be wrong. Rate this feedback:")
    if feedback_id is not None:
        r1, r2, r3, _ = st.columns([1, 1, 1, 3])
        if r1.button("Helpful", key=f"{key}_ok", icon=":material/thumb_up:"):
            repository.rate_feedback(feedback_id, "helpful")
            st.toast("Thanks - marked as helpful.")
        if r2.button("Wrong", key=f"{key}_bad", icon=":material/report:"):
            repository.rate_feedback(feedback_id, "wrong")
            st.toast("Marked as wrong. It will be ignored in your progress statistics.")
        if r3.button("Dismiss", key=f"{key}_dis", icon=":material/close:"):
            repository.rate_feedback(feedback_id, "dismissed")
            st.toast("Dismissed.")


def render_session_feedback(fb: dict) -> None:
    if not fb.get("ok"):
        st.warning(fb.get("error") or "Session feedback is not available.")
    else:
        if fb.get("summary"):
            st.markdown(fb["summary"])
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Strengths**")
            for s in fb.get("strengths", []) or ["-"]:
                st.markdown(f"- {s}")
        with c2:
            st.markdown("**To improve**")
            for s in fb.get("improvements", []) or ["-"]:
                st.markdown(f"- {s}")
        for key, label in (("clarity", "Clarity"), ("grammar", "Grammar"), ("relevance", "Relevance"),
                           ("structure", "Answer structure"), ("vocabulary", "Vocabulary")):
            if fb.get(key):
                st.markdown(f"**{label}:** {fb[key]}")
        if fb.get("next_steps"):
            st.markdown("**Next steps**\n" + "\n".join(f"- {s}" for s in fb["next_steps"]))
        st.caption("Written by the local AI model - treat it as a coach's opinion, not a test result.")
    stats = fb.get("stats") or {}
    if stats:
        st.markdown("**Measured statistics**")
        cols = st.columns(4)
        cols[0].metric("Answers", stats.get("user_turns", 0))
        cols[1].metric("Words", stats.get("total_words", 0))
        cols[2].metric("Avg words/min", stats.get("avg_wpm") or "-")
        cols[3].metric("Fillers / 100 words", stats.get("fillers_per_100_words") or "-")


def empty_state(text: str, icon: str = ":material/info:") -> None:
    st.info(text, icon=icon)


def _esc(text: str) -> str:
    import html

    return html.escape(text or "")
