"""Audio handling, missing models, Ollama client errors, pronunciation comparison,
validators and vocabulary parsing. All hardware and services are mocked."""

import io
import json
import wave

import numpy as np
import pytest
import requests

from audio.audio_utils import AudioError, analyze_quality, decode_wav, float_to_wav_bytes
from config.settings import AppSettings
from core import speech_recognition, speech_synthesis
from core.llm_client import (LLMTimeoutError, ModelNotInstalledError, OllamaClient, OllamaNotRunningError,
                             model_is_installed)
from core.pronunciation_analyzer import compare_transcript
from core.speech_recognition import ModelMissingError, SpeechRecognizer, WordTiming
from core.speech_synthesis import SpeechSynthesisError, SpeechSynthesizer, VoiceMissingError, clean_for_speech
from core.vocabulary_helper import VocabularyLookupError, lookup_word, parse_word_entry
from utils.validators import clean_word, extract_json_object


# ------------------------------------------------------------------ audio
def tone(seconds=1.0, rate=16000, amp=0.3):
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_wav_roundtrip_and_resample():
    data = float_to_wav_bytes(tone(1.0, 44100), 44100)
    audio = decode_wav(data)
    assert audio.dtype == np.float32 and abs(audio.size - 16000) <= 1


def test_stereo_is_converted_to_mono():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes((np.zeros((1600, 2)) + 1000).astype(np.int16).tobytes())
    assert decode_wav(buf.getvalue()).ndim == 1


@pytest.mark.parametrize("data", [b"", b"not a wav file at all"])
def test_invalid_audio_raises_friendly_error(data):
    with pytest.raises(AudioError):
        decode_wav(data)


def test_silence_detected():
    q = analyze_quality(np.zeros(16000, dtype=np.float32))
    assert q.is_silent and q.warnings


def test_clipping_detected():
    q = analyze_quality(np.ones(16000, dtype=np.float32))
    assert any("distorted" in w for w in q.warnings)


def test_normal_audio_ok():
    q = analyze_quality(tone())
    assert not q.is_silent and q.duration_s == 1.0


# ---------------------------------------------------- missing models / TTS
def test_missing_whisper_model_gives_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(speech_recognition, "WHISPER_MODELS_DIR", tmp_path)
    rec = SpeechRecognizer(AppSettings(whisper_model="base.en"))
    with pytest.raises(ModelMissingError, match="setup_linguaai.bat"):
        rec.transcribe(tone())


def test_empty_audio_returns_empty_transcript_without_loading():
    rec = SpeechRecognizer(AppSettings())
    result = rec.transcribe(np.zeros(0, dtype=np.float32))
    assert result.is_empty and not rec.is_loaded


def test_vad_finds_no_speech_in_silence():
    # Uses the Silero VAD model bundled inside the faster-whisper package (no download).
    assert speech_recognition.detect_speech_segments(np.zeros(32000, dtype=np.float32)) == []


def test_missing_piper_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(speech_synthesis, "PIPER_VOICES_DIR", tmp_path)
    synth = SpeechSynthesizer(AppSettings(tts_engine="piper", piper_voice="en_US-lessac-medium"))
    with pytest.raises(VoiceMissingError, match="Windows voice"):
        synth.synthesize("Hello")


def test_tts_empty_text():
    with pytest.raises(SpeechSynthesisError):
        SpeechSynthesizer(AppSettings()).synthesize("  ** ")


def test_windows_voice_unavailable_off_windows(monkeypatch):
    monkeypatch.setattr(speech_synthesis, "windows_tts_supported", lambda: False)
    with pytest.raises(SpeechSynthesisError, match="only available on Windows"):
        SpeechSynthesizer(AppSettings(tts_engine="windows")).synthesize("Hello")


def test_clean_for_speech():
    assert clean_for_speech("**Great** job! 🎉") == "Great job!"


# ------------------------------------------------------------- ollama client
class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text or json.dumps(payload or {})
        self.content = self.text.encode()

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response, self.exc, self.trust_env, self.posted = response, exc, True, None

    def get(self, url, timeout):
        if self.exc:
            raise self.exc
        return self.response

    def post(self, url, json, timeout):
        self.posted = json
        if self.exc:
            raise self.exc
        return self.response


def test_ollama_not_running():
    client = OllamaClient(AppSettings(), session=FakeSession(exc=requests.exceptions.ConnectionError()))
    with pytest.raises(OllamaNotRunningError):
        client.chat([{"role": "user", "content": "hi"}])
    status = client.status()
    assert not status.running and "not running" in status.message


def test_ollama_model_missing():
    client = OllamaClient(AppSettings(), session=FakeSession(FakeResponse(404, {"error": "model not found"})))
    with pytest.raises(ModelNotInstalledError, match="ollama pull"):
        client.chat([{"role": "user", "content": "hi"}])


def test_ollama_timeout():
    client = OllamaClient(AppSettings(), session=FakeSession(exc=requests.exceptions.Timeout()))
    with pytest.raises(LLMTimeoutError):
        client.chat([{"role": "user", "content": "hi"}])


def test_ollama_success_and_payload():
    session = FakeSession(FakeResponse(200, {"message": {"role": "assistant", "content": " Hello! "}}))
    client = OllamaClient(AppSettings(), session=session)
    assert client.chat([{"role": "user", "content": "hi"}], json_mode=True) == "Hello!"
    assert session.posted["format"] == "json" and session.posted["stream"] is False
    assert session.trust_env is False   # never route local traffic through a proxy


def test_ollama_status_lists_models():
    session = FakeSession(FakeResponse(200, {"models": [{"name": "llama3.2:3b"}]}))
    status = OllamaClient(AppSettings(), session=session).status()
    assert status.running and status.model_ready


def test_remote_host_refused():
    s = AppSettings()
    s.ollama_host = "http://example.com:11434"
    with pytest.raises(ValueError):
        OllamaClient(s)


def test_model_name_matching():
    assert model_is_installed("llama3.2", ["llama3.2:latest"])
    assert not model_is_installed("llama3.2:3b", ["llama3.2:1b"])


# ------------------------------------------------------------ pronunciation
def test_pronunciation_comparison():
    ref = "I think this is the third time"
    heard = "I sink this is third time today"
    timings = [WordTiming(w, i, i + 0.5, 0.9 if w != "this" else 0.3) for i, w in enumerate(heard.split())]
    r = compare_transcript(ref, heard, timings)
    assert ("think", "sink") in r.different
    assert "the" in r.missing
    assert "this" in r.unsure
    assert 0 < r.transcript_match < 1
    assert any(tag == "th" for tag, _ in r.practice_tags)


def test_pronunciation_perfect_and_empty():
    assert compare_transcript("Hello there.", "hello, there").transcript_match == 1.0
    r = compare_transcript("Hello there", "")
    assert r.transcript_match == 0 and r.missing == ["hello", "there"]


# ------------------------------------------------------- validators / vocab
def test_extract_json_object():
    assert extract_json_object('noise {"a": 1} noise') == {"a": 1}
    assert extract_json_object("[1, 2]") is None
    assert extract_json_object(None) is None


@pytest.mark.parametrize("bad", ["", "   ", "x" * 61, "drop table;", "123"])
def test_clean_word_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        clean_word(bad)


def test_clean_word_accepts_phrases():
    assert clean_word("  figure   out ") == "figure out"
    assert clean_word("well-known") == "well-known"


def test_vocab_parse(fake_llm):
    raw = json.dumps({"definition": "at the same time", "synonyms": "simultaneously", "register": "Neutral"})
    entry = parse_word_entry("meanwhile", raw)
    assert entry.synonyms == ["simultaneously"] and entry.register == "neutral"
    with pytest.raises(VocabularyLookupError):
        parse_word_entry("x", '{"definition": ""}')
    llm = fake_llm([raw])
    assert lookup_word(llm, "meanwhile").definition == "at the same time"
    with pytest.raises(ValueError):
        lookup_word(llm, "<script>")
