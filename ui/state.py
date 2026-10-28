"""
Shared Streamlit state: settings, profile and the (expensive) model objects.

``st.cache_resource`` keeps one SpeechRecognizer / SpeechSynthesizer alive
between page reloads, so models are not re-loaded for every sentence.
``max_entries=1`` means that when you change the model in Settings, the old
model is released instead of both staying in memory.
"""

from __future__ import annotations

import streamlit as st

from config.settings import AppSettings
from core.llm_client import OllamaClient, OllamaStatus
from core.learning_engine import DEFAULT_PROFILE
from core.performance_monitor import PerformanceMonitor
from core.speech_recognition import SpeechRecognizer
from core.speech_synthesis import SpeechSynthesizer
from database import repository


def get_settings() -> AppSettings:
    return AppSettings.load()


def get_profile() -> dict:
    profile = dict(DEFAULT_PROFILE)
    stored = repository.get_preference("profile", {}) or {}
    if isinstance(stored, dict):
        profile.update({k: v for k, v in stored.items() if k in DEFAULT_PROFILE})
    return profile


def save_profile(profile: dict) -> None:
    repository.set_preference("profile", {k: profile.get(k, v) for k, v in DEFAULT_PROFILE.items()})


@st.cache_resource(max_entries=1, show_spinner=False)
def _recognizer(model: str, device: str, compute: str, beam: int, keep_fillers: bool) -> SpeechRecognizer:
    s = AppSettings(whisper_model=model, whisper_device=device, whisper_compute_type=compute,
                    whisper_beam_size=beam, keep_filler_words=keep_fillers)
    return SpeechRecognizer(s)


def get_recognizer(settings: AppSettings) -> SpeechRecognizer:
    return _recognizer(settings.whisper_model, settings.whisper_device, settings.whisper_compute_type,
                       settings.whisper_beam_size, settings.keep_filler_words)


@st.cache_resource(max_entries=1, show_spinner=False)
def _synthesizer(engine: str, voice: str, rate: float) -> SpeechSynthesizer:
    return SpeechSynthesizer(AppSettings(tts_engine=engine, piper_voice=voice, speech_rate=rate))


def get_synthesizer(settings: AppSettings) -> SpeechSynthesizer:
    return _synthesizer(settings.tts_engine, settings.piper_voice, settings.speech_rate)


def get_llm(settings: AppSettings) -> OllamaClient:
    return OllamaClient(settings)


@st.cache_data(ttl=15, show_spinner=False)
def ollama_status(host: str, model: str) -> OllamaStatus:
    """Cached for 15 s so we don't ping Ollama on every click."""
    return OllamaClient(AppSettings(ollama_host=host, ollama_model=model)).status()


def get_monitor() -> PerformanceMonitor:
    if "perf_monitor" not in st.session_state:
        st.session_state.perf_monitor = PerformanceMonitor()
    return st.session_state.perf_monitor


def clear_model_caches() -> None:
    _recognizer.clear()
    _synthesizer.clear()
    ollama_status.clear()
