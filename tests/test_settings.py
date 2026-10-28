"""Settings loading, validation and saving."""

import json

from config.settings import AppSettings, is_local_url


def test_defaults_when_file_missing(tmp_path):
    s = AppSettings.load(tmp_path / "nope.json")
    assert s.whisper_model == "base.en" and s.load_warnings == []


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    s = AppSettings(whisper_model="tiny.en", speech_rate=1.2, save_history=False)
    assert s.save(path) == []
    loaded = AppSettings.load(path)
    assert loaded.whisper_model == "tiny.en" and loaded.speech_rate == 1.2 and loaded.save_history is False


def test_invalid_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"whisper_model": "gigantic", "speech_rate": 9, "context_turns": "many",
                                "save_history": "yes", "mystery": 1}))
    s = AppSettings.load(path)
    assert s.whisper_model == "base.en" and s.speech_rate == 1.0 and s.context_turns == 8
    assert s.save_history is True
    assert len(s.load_warnings) >= 4


def test_corrupted_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ not json")
    s = AppSettings.load(path)
    assert s.ollama_model == "llama3.2:3b" and s.load_warnings


def test_remote_ollama_host_is_rejected(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"ollama_host": "https://api.example.com"}))
    s = AppSettings.load(path)
    assert s.ollama_host == "http://127.0.0.1:11434"
    assert any("this computer" in w for w in s.load_warnings)


def test_is_local_url():
    assert is_local_url("http://localhost:11434")
    assert is_local_url("http://127.0.0.1:11434")
    assert not is_local_url("http://192.168.1.5:11434")
    assert not is_local_url("not a url")


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("LINGUAAI_OLLAMA_MODEL", "qwen2.5:1.5b")
    assert AppSettings.load(tmp_path / "none.json").ollama_model == "qwen2.5:1.5b"
