"""
Application settings for LinguaAI.

There are two kinds of settings:

1. Technical settings (models, limits, timeouts) live in ``data/settings.json``.
   They are loaded into the ``AppSettings`` dataclass below. Any missing or
   invalid value falls back to a safe default, and the problem is reported in
   ``AppSettings.load_warnings`` so the user can see it in the Settings page.

2. The learning profile (proficiency, goals ...) lives in the SQLite database
   (see ``database/repository.py``) because it is part of the user's history.

A few values can also be overridden with environment variables (see
``.env.example``), which is handy for testing.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Important folders. Everything is relative to the project folder so the
# project can live anywhere (for example on the Desktop).
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"
WHISPER_MODELS_DIR = MODELS_DIR / "whisper"
PIPER_VOICES_DIR = MODELS_DIR / "piper"
LOGS_DIR = PROJECT_ROOT / "logs"
EXERCISES_DIR = DATA_DIR / "exercises"
SETTINGS_FILE = DATA_DIR / "settings.json"
DATABASE_FILE = DATA_DIR / "linguaai.db"

# ---------------------------------------------------------------------------
# Allowed choices. Keeping them here means the UI and the validator agree.
# ---------------------------------------------------------------------------
WHISPER_MODEL_CHOICES = {
    # name: (approximate download size, short description)
    "tiny.en": ("~75 MB", "Fastest, least accurate. Good for very slow laptops."),
    "base.en": ("~145 MB", "Recommended default for 8 GB RAM laptops."),
    "small.en": ("~480 MB", "More accurate, roughly 2-3x slower than base on CPU."),
}
WHISPER_DEVICE_CHOICES = ("auto", "cpu", "cuda")
WHISPER_COMPUTE_CHOICES = ("int8", "int8_float16", "float16", "float32")
TTS_ENGINE_CHOICES = ("piper", "windows")
PIPER_VOICE_SUGGESTIONS = {
    "en_US-lessac-medium": "American English, clear female voice (~63 MB)",
    "en_US-ryan-medium": "American English, male voice (~63 MB)",
    "en_GB-alba-medium": "British English (Scottish), female voice (~63 MB)",
    "en_GB-northern_english_male-medium": "British English, male voice (~63 MB)",
}
OLLAMA_MODEL_SUGGESTIONS = {
    "llama3.2:3b": "Recommended. ~2.0 GB download, ~3-4 GB RAM while running.",
    "qwen2.5:1.5b": "Lighter. ~1.0 GB download, ~2 GB RAM. Weaker grammar feedback.",
    "llama3.2:1b": "Lightest. ~1.3 GB download. Feedback quality is noticeably lower.",
}
ENGLISH_VARIETIES = ("American", "British")
FEEDBACK_FREQUENCIES = {
    "every_turn": "After every response",
    "every_3_turns": "After every 3 responses",
    "end_of_session": "At the end of the conversation",
    "on_request": "Only when I ask",
}


@dataclass
class AppSettings:
    """All technical settings with conservative defaults for an 8 GB laptop."""

    # Speech recognition (Faster-Whisper)
    whisper_model: str = "base.en"
    whisper_device: str = "auto"          # auto = use CUDA only if it really works
    whisper_compute_type: str = "int8"    # int8 is the lightest option on CPU
    whisper_beam_size: int = 1            # 1 = greedy decoding, fastest
    keep_filler_words: bool = True        # nudge Whisper to keep "um", "uh"

    # Local language model (Ollama)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: int = 120
    ollama_context_tokens: int = 2048     # smaller context = less RAM
    ollama_keep_alive: str = "10m"        # how long Ollama keeps the model in RAM
    max_reply_tokens: int = 220

    # Text-to-speech
    tts_engine: str = "piper"             # "piper" or "windows" (built-in voice)
    piper_voice: str = "en_US-lessac-medium"
    speech_rate: float = 1.0              # 0.5 (slow) .. 1.5 (fast)
    autoplay_replies: bool = True

    # Conversation behaviour
    context_turns: int = 8                # how many previous messages the AI sees
    max_recording_seconds: int = 60
    min_recording_seconds: float = 0.6
    long_pause_seconds: float = 1.0
    save_history: bool = True

    # Filled in by load(): problems found while reading the settings file
    load_warnings: list[str] = field(default_factory=list, repr=False)

    # ----------------------------------------------------------------- helpers
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("load_warnings", None)
        return data

    def validate(self) -> list[str]:
        """Fix invalid values in place and return a list of human-readable warnings."""
        warnings: list[str] = []
        defaults = AppSettings()

        def reset(name: str, reason: str) -> None:
            warnings.append(f"Setting '{name}' {reason}; using default {getattr(defaults, name)!r}.")
            setattr(self, name, getattr(defaults, name))

        if self.whisper_model not in WHISPER_MODEL_CHOICES and not Path(self.whisper_model).is_dir():
            reset("whisper_model", f"has unknown value {self.whisper_model!r}")
        if self.whisper_device not in WHISPER_DEVICE_CHOICES:
            reset("whisper_device", f"has unknown value {self.whisper_device!r}")
        if self.whisper_compute_type not in WHISPER_COMPUTE_CHOICES:
            reset("whisper_compute_type", f"has unknown value {self.whisper_compute_type!r}")
        if not 1 <= int(self.whisper_beam_size) <= 5:
            reset("whisper_beam_size", "must be between 1 and 5")
        if self.tts_engine not in TTS_ENGINE_CHOICES:
            reset("tts_engine", f"has unknown value {self.tts_engine!r}")
        if not 0.5 <= float(self.speech_rate) <= 1.5:
            reset("speech_rate", "must be between 0.5 and 1.5")
        if not 2 <= int(self.context_turns) <= 30:
            reset("context_turns", "must be between 2 and 30")
        if not 5 <= int(self.max_recording_seconds) <= 300:
            reset("max_recording_seconds", "must be between 5 and 300")
        if not 0.1 <= float(self.min_recording_seconds) <= 5:
            reset("min_recording_seconds", "must be between 0.1 and 5")
        if not 0.3 <= float(self.long_pause_seconds) <= 5:
            reset("long_pause_seconds", "must be between 0.3 and 5")
        if not 10 <= int(self.ollama_timeout_seconds) <= 600:
            reset("ollama_timeout_seconds", "must be between 10 and 600")
        if not 512 <= int(self.ollama_context_tokens) <= 32768:
            reset("ollama_context_tokens", "must be between 512 and 32768")
        if not 50 <= int(self.max_reply_tokens) <= 2000:
            reset("max_reply_tokens", "must be between 50 and 2000")
        if not str(self.ollama_model).strip():
            reset("ollama_model", "is empty")
        if not str(self.piper_voice).strip():
            reset("piper_voice", "is empty")
        # Security: the language model must run on this computer only.
        if not is_local_url(self.ollama_host):
            reset("ollama_host", "must point to this computer (localhost/127.0.0.1)")
        return warnings

    # ------------------------------------------------------------- load / save
    @classmethod
    def load(cls, path: Path | None = None) -> "AppSettings":
        """Load settings from JSON. Never crashes: bad files fall back to defaults."""
        path = path or SETTINGS_FILE
        settings = cls()
        warnings: list[str] = []
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("top level is not a JSON object")
            except (OSError, ValueError) as exc:
                warnings.append(f"Could not read {path.name} ({exc}); using defaults.")
                raw = {}
            known = {f.name: f for f in fields(cls) if f.name != "load_warnings"}
            for key, value in raw.items():
                if key not in known:
                    warnings.append(f"Ignoring unknown setting {key!r}.")
                    continue
                default_value = getattr(settings, key)
                try:
                    setattr(settings, key, _coerce(value, type(default_value)))
                except (TypeError, ValueError):
                    warnings.append(f"Setting {key!r} has the wrong type; using default.")
        _apply_env_overrides(settings)
        warnings.extend(settings.validate())
        settings.load_warnings = warnings
        for w in warnings:
            logger.warning(w)
        return settings

    def save(self, path: Path | None = None) -> list[str]:
        """Validate and save to JSON. Returns any warnings produced by validation."""
        path = path or SETTINGS_FILE
        warnings = self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic replace: never leaves a half-written file
        return warnings


def _coerce(value: Any, target: type) -> Any:
    """Convert a JSON value to the type of the default value."""
    if target is bool:
        if isinstance(value, bool):
            return value
        raise TypeError("expected true/false")
    if target is int:
        if isinstance(value, bool):
            raise TypeError("expected a number")
        return int(value)
    if target is float:
        if isinstance(value, bool):
            raise TypeError("expected a number")
        return float(value)
    if target is str:
        if not isinstance(value, str):
            raise TypeError("expected text")
        return value
    return value


def _apply_env_overrides(settings: AppSettings) -> None:
    """Environment variables override the file (useful for tests and power users)."""
    if host := os.environ.get("LINGUAAI_OLLAMA_HOST"):
        settings.ollama_host = host
    if model := os.environ.get("LINGUAAI_OLLAMA_MODEL"):
        settings.ollama_model = model
    if whisper := os.environ.get("LINGUAAI_WHISPER_MODEL"):
        settings.whisper_model = whisper


def is_local_url(url: str) -> bool:
    """True if a URL points at this computer."""
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return host in {"127.0.0.1", "localhost", "::1"}


def database_path() -> Path:
    """Database location (can be overridden in tests with LINGUAAI_DB)."""
    override = os.environ.get("LINGUAAI_DB")
    return Path(override) if override else DATABASE_FILE
