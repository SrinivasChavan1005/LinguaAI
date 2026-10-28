"""Pronunciation Lab: hear a sentence, repeat it, compare what was recognised."""

import hashlib
import json

import streamlit as st

from audio.audio_utils import AudioError, analyze_quality, decode_wav
from config.settings import EXERCISES_DIR
from core.pronunciation_analyzer import compare_transcript
from core.speech_recognition import SpeechRecognitionError, whisper_model_available
from core.speech_synthesis import SpeechSynthesisError
from database import repository
from ui import components, state


@st.cache_data(show_spinner=False)
def load_sets() -> dict:
    try:
        return json.loads((EXERCISES_DIR / "pronunciation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"general": {"label": "Everyday sentences", "sentences": ["Thank you for your help."]}}


st.title("Pronunciation Lab")
st.info("**How to read the results:** LinguaAI compares the sentence you were given with what the "
        "speech recogniser heard. This shows words that may need attention, but it is **not** a "
        "sound-by-sound pronunciation score - recognition can also fail because of noise or the "
        "microphone.", icon=":material/info:")

settings = state.get_settings()
sets = load_sets()
ss = st.session_state
ss.setdefault("pron_mic", 0)
ss.setdefault("pron_result", None)
ss.setdefault("pron_seen", set())

custom = ss.get("pron_custom_sentence")
options = list(sets)
default_set = ss.get("pron_set", "general")
c1, c2 = st.columns([1, 2])
set_key = c1.selectbox("Practice set", options, format_func=lambda k: sets[k]["label"],
                       index=options.index(default_set) if default_set in options else 0)
ss["pron_set"] = set_key
sentence_choices = list(sets[set_key]["sentences"])
if custom:
    sentence_choices = [custom] + sentence_choices
sentence = c2.selectbox("Sentence", sentence_choices)
own = st.text_input("...or type your own sentence", max_chars=200)
reference = (own or sentence).strip()

st.markdown(f"### _{reference}_")
b1, b2 = st.columns([1, 4])
if b1.button("Hear it", icon=":material/volume_up:"):
    try:
        wav, _ = state.get_synthesizer(settings).synthesize(reference)
        ss["pron_ref_audio"] = (reference, wav)
    except SpeechSynthesisError as exc:
        st.warning(f"Voice unavailable: {exc}")
ref_audio = ss.get("pron_ref_audio")
if ref_audio and ref_audio[0] == reference:
    st.audio(ref_audio[1], format="audio/wav", autoplay=True)

if not whisper_model_available(settings.whisper_model):
    st.error(f"Speech recognition model '{settings.whisper_model}' is not downloaded. Run setup_linguaai.bat.")
    st.stop()

audio = st.audio_input("Record yourself saying the sentence", key=f"pron_mic_{ss['pron_mic']}", sample_rate=16000)
if audio is not None:
    data = audio.getvalue()
    digest = hashlib.sha1(data).hexdigest()
    if digest not in ss["pron_seen"]:
        ss["pron_seen"].add(digest)
        result = {"reference": reference, "error": None}
        try:
            samples = decode_wav(data)
            quality = analyze_quality(samples)
            if quality.is_silent:
                raise AudioError(" ".join(quality.warnings))
            with st.spinner("Recognising your speech..."):
                transcript = state.get_recognizer(settings).transcribe(samples[: settings.max_recording_seconds * 16000])
            comparison = compare_transcript(reference, transcript.text, transcript.words)
            result.update(comparison=comparison.to_dict(), quality=quality.__dict__, audio=data,
                          speaking=round(sum(e - s for s, e in transcript.speech_segments), 2))
            repository.add_attempt("pronunciation", reference, transcript.text,
                                   {"transcript_match": comparison.transcript_match,
                                    "missing": comparison.missing, "different": comparison.different,
                                    "unsure": comparison.unsure})
        except (AudioError, SpeechRecognitionError) as exc:
            result["error"] = str(exc)
        ss["pron_result"] = result
        ss["pron_mic"] += 1
        st.rerun()

res = ss.get("pron_result")
if res:
    st.divider()
    if res.get("error"):
        st.error(res["error"])
    else:
        comp = res["comparison"]
        st.markdown("**Your recording** (kept only until you leave this page - never saved):")
        st.audio(res["audio"], format="audio/wav")
        st.markdown(f"**Recognised:** {comp['recognized_text'] or '(nothing)'}")
        html = []
        for w in comp["words"]:
            unsure = w["probability"] is not None and w["probability"] < 0.5
            cls = "unsure" if w["status"] == "match" and unsure else w["status"]
            text = w["reference"] or w["heard"]
            if w["status"] == "different":
                text = f"{w['reference']} → {w['heard']}"
            html.append(f'<span class="la-word la-w-{cls}">{components._esc(text)}</span>')
        st.markdown("".join(html), unsafe_allow_html=True)
        st.caption("Green = recognised · Orange = recognised, but the recogniser was unsure · "
                   "Red = missing or heard as a different word · Grey italic = extra word")
        q = res["quality"]
        m = st.columns(4)
        m[0].metric("Transcript match", f"{comp['transcript_match'] * 100:.0f}%",
                    help="Share of the sentence's words that were recognised exactly. Approximate.")
        m[1].metric("Speaking time", f"{res['speaking']:.1f}s", help=f"Recording length: {q['duration_s']:.1f}s")
        m[2].metric("Loudness", f"{q['rms_dbfs']:.0f} dBFS", help="Around -30 to -15 dBFS is comfortable.")
        m[3].metric("Distortion", "Yes" if q["clipping_ratio"] > 0.01 else "No")
        for w in q["warnings"]:
            st.warning(w)
        if comp["missing"] or comp["different"] or comp["unsure"]:
            st.markdown("**Words to practise:** " + ", ".join(
                comp["missing"] + [r for r, _ in comp["different"]] + comp["unsure"]))
        tags = [t for t in comp["practice_tags"] if t[0] in sets and t[0] != set_key]
        if tags:
            st.markdown("**Suggested practice sets** (based on the spelling of those words - a hint, not a diagnosis):")
            cols = st.columns(len(tags))
            for col, (tag, label) in zip(cols, tags):
                if col.button(label, key=f"tag_{tag}"):
                    ss["pron_set"] = tag
                    ss["pron_result"] = None
                    st.rerun()

with st.expander("Recent attempts"):
    attempts = repository.list_attempts("pronunciation", limit=20)
    if not attempts:
        st.caption("No attempts yet.")
    else:
        st.dataframe([{"When": a["created_at"], "Sentence": a["reference"],
                       "Match": f"{a['result'].get('transcript_match', 0) * 100:.0f}%"} for a in attempts],
                     hide_index=True)
