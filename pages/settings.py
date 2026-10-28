"""Settings: learning profile, models, behaviour and diagnostics."""

import time

import streamlit as st

from config.settings import (OLLAMA_MODEL_SUGGESTIONS, PIPER_VOICE_SUGGESTIONS, SETTINGS_FILE, TTS_ENGINE_CHOICES,
                             WHISPER_COMPUTE_CHOICES, WHISPER_DEVICE_CHOICES, WHISPER_MODEL_CHOICES)
from core.llm_client import LLMError
from core.performance_monitor import ollama_process_memory_mb, process_memory_mb, system_memory
from core.speech_recognition import SpeechRecognitionError, whisper_model_available
from core.speech_synthesis import SpeechSynthesisError, installed_piper_voices, windows_tts_supported
from ui import state
from ui.profile_form import profile_form
from utils.system_checks import run_all_checks

st.title("Settings")
settings = state.get_settings()
for w in settings.load_warnings:
    st.warning(w)

tab_profile, tab_models, tab_behaviour, tab_diag = st.tabs(
    ["Learning profile", "Models", "Conversation", "Diagnostics"])

with tab_profile:
    new = profile_form(state.get_profile(), "Save profile")
    if new:
        state.save_profile(new)
        st.success("Profile saved. New sessions will use it.")

with tab_models:
    st.caption("Models are only read from the `models` folder. Changing a model here never downloads "
               "anything - use `setup_linguaai.bat` (with internet) to add models.")
    status = state.ollama_status(settings.ollama_host, settings.ollama_model)
    with st.form("models"):
        st.markdown("##### Speech recognition (Faster-Whisper)")
        c1, c2, c3 = st.columns(3)
        names = list(WHISPER_MODEL_CHOICES)
        whisper_model = c1.selectbox(
            "Model", names, index=names.index(settings.whisper_model) if settings.whisper_model in names else 1,
            format_func=lambda n: f"{n} ({WHISPER_MODEL_CHOICES[n][0]})"
                                  + ("" if whisper_model_available(n) else " - not downloaded"),
            help="\n".join(f"- {n}: {d}" for n, (_, d) in WHISPER_MODEL_CHOICES.items()))
        whisper_device = c2.selectbox("Device", WHISPER_DEVICE_CHOICES,
                                      index=WHISPER_DEVICE_CHOICES.index(settings.whisper_device),
                                      help="'auto' uses an NVIDIA GPU only if it works, otherwise CPU.")
        compute = c3.selectbox("Precision", WHISPER_COMPUTE_CHOICES,
                               index=WHISPER_COMPUTE_CHOICES.index(settings.whisper_compute_type),
                               help="int8 is the fastest and lightest on CPU.")
        keep_fillers = st.checkbox("Keep filler words (um, uh) in transcripts", settings.keep_filler_words,
                                   help="Needed for filler-word statistics.")

        st.markdown("##### Language model (Ollama)")
        installed = status.installed_models if status.running else []
        options = sorted(set(installed) | {settings.ollama_model})
        llm = st.selectbox("Model", options, index=options.index(settings.ollama_model),
                           format_func=lambda m: m + ("" if m in installed or f"{m}:latest" in installed
                                                      else " - not installed"))
        st.caption("Suggestions: " + " · ".join(f"`{m}` {d}" for m, d in OLLAMA_MODEL_SUGGESTIONS.items()))
        ctx = st.select_slider("Context window (tokens)", [1024, 2048, 4096, 8192], value=settings.ollama_context_tokens
                               if settings.ollama_context_tokens in (1024, 2048, 4096, 8192) else 2048,
                               help="Bigger = remembers more but uses more RAM.")

        st.markdown("##### Voice")
        c1, c2 = st.columns(2)
        engine = c1.radio("Engine", TTS_ENGINE_CHOICES, index=TTS_ENGINE_CHOICES.index(settings.tts_engine),
                          format_func=lambda e: "Piper (natural)" if e == "piper" else "Windows built-in",
                          horizontal=True)
        voices = sorted(set(installed_piper_voices()) | {settings.piper_voice} | set(PIPER_VOICE_SUGGESTIONS))
        voice = c2.selectbox("Piper voice", voices, index=voices.index(settings.piper_voice),
                             format_func=lambda v: v + ("" if v in installed_piper_voices() else " - not downloaded"))
        rate = st.slider("Speaking speed", 0.5, 1.5, float(settings.speech_rate), 0.05)
        autoplay = st.checkbox("Play AI replies automatically", settings.autoplay_replies)
        if st.form_submit_button("Save model settings", type="primary"):
            settings.whisper_model, settings.whisper_device = whisper_model, whisper_device
            settings.whisper_compute_type, settings.keep_filler_words = compute, keep_fillers
            settings.ollama_model, settings.ollama_context_tokens = llm, ctx
            settings.tts_engine, settings.piper_voice = engine, voice
            settings.speech_rate, settings.autoplay_replies = rate, autoplay
            for w in settings.save():
                st.warning(w)
            if engine == "windows" and not windows_tts_supported():
                st.warning("The Windows voice only works on Windows.")
            state.clear_model_caches()
            st.success(f"Saved to {SETTINGS_FILE.name}. Models reload on next use.")

with tab_behaviour:
    with st.form("behaviour"):
        context = st.slider("How many previous messages the AI remembers", 2, 30, settings.context_turns)
        max_rec = st.slider("Maximum recording length (seconds)", 10, 300, settings.max_recording_seconds, 5)
        pause = st.slider("Count a pause as 'long' after (seconds)", 0.5, 3.0, float(settings.long_pause_seconds), 0.1)
        reply_tokens = st.slider("Maximum AI reply length (tokens)", 80, 600, settings.max_reply_tokens, 20)
        save_history = st.checkbox("Save conversation history on this computer", settings.save_history,
                                   help="Audio is never saved. Text and metrics are stored in data/linguaai.db.")
        if st.form_submit_button("Save", type="primary"):
            settings.context_turns, settings.max_recording_seconds = context, max_rec
            settings.long_pause_seconds, settings.max_reply_tokens = pause, reply_tokens
            settings.save_history = save_history
            for w in settings.save():
                st.warning(w)
            st.success("Saved. Applies to new sessions.")

with tab_diag:
    st.markdown("##### System check")
    if st.button("Run system check", icon=":material/fact_check:"):
        icons = {"ok": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}
        st.dataframe([{"": icons[c.status], "Check": c.name, "Result": c.detail, "How to fix": c.fix}
                      for c in run_all_checks()], hide_index=True)

    st.markdown("##### Memory")
    sysmem = system_memory()
    c = st.columns(3)
    c[0].metric("LinguaAI process", f"{process_memory_mb() or 0:.0f} MB",
                help="Includes the speech model and Piper voice once loaded.")
    oll = ollama_process_memory_mb()
    c[1].metric("Ollama processes", f"{oll:.0f} MB" if oll else "-", help="The language model lives here.")
    if sysmem:
        c[2].metric("System RAM available", f"{sysmem['available_gb']} / {sysmem['total_gb']} GB")

    st.markdown("##### Measured timings (this browser session)")
    monitor = state.get_monitor()
    avg = monitor.averages()
    c = st.columns(5)
    for col, (key, label) in zip(c, [("asr_seconds", "Speech→text"), ("llm_seconds", "AI reply"),
                                     ("tts_seconds", "Voice"), ("grammar_seconds", "Grammar"),
                                     ("total_seconds", "End-to-end")]):
        col.metric(label, f"{avg[key]:.1f}s" if avg[key] is not None else "-")
    st.caption(f"Based on {len(monitor.history)} turn(s). App startup: {monitor.startup_seconds}s. "
               "End-to-end = from receiving your recording until the reply audio is ready.")

    st.markdown("##### Component tests")
    st.caption("Each button runs the real local component once and measures it.")
    b1, b2, b3 = st.columns(3)
    if b1.button("Test speech model load"):
        rec = state.get_recognizer(settings)
        try:
            was_loaded = rec.is_loaded
            rec.load()
            note = "already loaded" if was_loaded else f"loaded in {rec.load_seconds:.1f}s"
            st.success(f"Speech model '{settings.whisper_model}' on {rec.device_used}: {note}.")
            if rec.notice:
                st.info(rec.notice)
        except SpeechRecognitionError as exc:
            st.error(str(exc))
    if b2.button("Test AI model"):
        try:
            t = time.perf_counter()
            reply = state.get_llm(settings).chat(
                [{"role": "user", "content": "Say hello to an English learner in one short sentence."}],
                max_tokens=40)
            st.success(f"{time.perf_counter() - t:.1f}s: {reply}")
        except LLMError as exc:
            st.error(str(exc))
    if b3.button("Test voice"):
        try:
            wav, secs = state.get_synthesizer(settings).synthesize(
                "Hello! This is your LinguaAI voice. Everything is running on your computer.")
            st.success(f"Generated in {secs:.1f}s")
            st.audio(wav, format="audio/wav", autoplay=True)
        except SpeechSynthesisError as exc:
            st.error(str(exc))
