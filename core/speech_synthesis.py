"""
Local text-to-speech (TTS).

Two engines, both fully offline:

* ``piper``   - natural neural voices (Piper). Needs a voice file in
                ``models/piper/<voice>.onnx`` + ``<voice>.onnx.json``.
* ``windows`` - the voice built into Windows (System.Speech via PowerShell).
                Sounds more robotic but needs no download.

The engine is chosen in Settings. If the selected engine fails we raise an
error that says so; we never silently switch to another engine.

Both engines return WAV bytes which the page plays in the browser.
"""

from __future__ import annotations

import io
import logging
import os
import platform
import re
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

from config.settings import PIPER_VOICES_DIR, AppSettings

logger = logging.getLogger(__name__)

MAX_TTS_CHARS = 1200  # protect against very long model replies


class SpeechSynthesisError(Exception):
    pass


class VoiceMissingError(SpeechSynthesisError):
    pass


def piper_voice_paths(voice: str) -> tuple[Path, Path]:
    return PIPER_VOICES_DIR / f"{voice}.onnx", PIPER_VOICES_DIR / f"{voice}.onnx.json"


def piper_voice_available(voice: str) -> bool:
    model, config = piper_voice_paths(voice)
    return model.is_file() and config.is_file()


def installed_piper_voices() -> list[str]:
    if not PIPER_VOICES_DIR.is_dir():
        return []
    return sorted(p.name[: -len(".onnx")] for p in PIPER_VOICES_DIR.glob("*.onnx")
                  if (p.parent / f"{p.name}.json").is_file())


def clean_for_speech(text: str) -> str:
    """Remove markdown symbols and emojis that sound odd when read aloud."""
    text = re.sub(r"[*_#`>~]+", " ", text)
    text = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_TTS_CHARS]


class SpeechSynthesizer:
    """Create once, reuse. The Piper voice is loaded lazily on first use."""

    def __init__(self, settings: AppSettings):
        self.engine = settings.tts_engine
        self.voice_name = settings.piper_voice
        self.rate = settings.speech_rate
        self._voice = None
        self._lock = threading.Lock()

    def synthesize(self, text: str) -> tuple[bytes, float]:
        """Return (wav_bytes, seconds_taken)."""
        text = clean_for_speech(text)
        if not text:
            raise SpeechSynthesisError("There is no text to speak.")
        started = time.perf_counter()
        if self.engine == "piper":
            wav = self._synthesize_piper(text)
        elif self.engine == "windows":
            wav = synthesize_windows(text, self.rate)
        else:
            raise SpeechSynthesisError(f"Unknown TTS engine '{self.engine}'.")
        elapsed = time.perf_counter() - started
        logger.info("TTS (%s) produced %d bytes in %.2fs", self.engine, len(wav), elapsed)
        return wav, elapsed

    # ------------------------------------------------------------------ piper
    def _load_piper(self):
        if self._voice is not None:
            return self._voice
        model, config = piper_voice_paths(self.voice_name)
        if not (model.is_file() and config.is_file()):
            raise VoiceMissingError(
                f"Piper voice '{self.voice_name}' was not found in {PIPER_VOICES_DIR}. "
                "Run setup_linguaai.bat to download it, or switch to the built-in Windows "
                "voice in Settings."
            )
        try:
            from piper import PiperVoice

            self._voice = PiperVoice.load(model, config_path=config)
        except Exception as exc:  # onnxruntime raises its own exception types
            raise SpeechSynthesisError(
                f"Could not load Piper voice '{self.voice_name}'. The file may be corrupted; "
                f"delete it and run setup again. Details: {str(exc)[:200]}"
            ) from exc
        return self._voice

    def _synthesize_piper(self, text: str) -> bytes:
        from piper.config import SynthesisConfig

        with self._lock:
            voice = self._load_piper()
            # length_scale > 1 = slower speech, < 1 = faster.
            config = SynthesisConfig(length_scale=1.0 / max(self.rate, 0.1))
            buf = io.BytesIO()
            try:
                with wave.open(buf, "wb") as wav_file:
                    voice.synthesize_wav(text, wav_file, syn_config=config)
            except Exception as exc:
                raise SpeechSynthesisError(f"Piper could not speak this text: {str(exc)[:200]}") from exc
        return buf.getvalue()


# ---------------------------------------------------------------------------
# Windows built-in voice
# ---------------------------------------------------------------------------
_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [System.IO.File]::ReadAllText($env:LINGUAAI_TTS_IN, [System.Text.Encoding]::UTF8)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = [int]$env:LINGUAAI_TTS_RATE
$s.SetOutputToWaveFile($env:LINGUAAI_TTS_OUT)
$s.Speak($text)
$s.Dispose()
"""


def windows_tts_supported() -> bool:
    return platform.system() == "Windows"


def synthesize_windows(text: str, rate: float = 1.0, timeout: int = 60) -> bytes:
    """Use Windows' built-in voice. Text is passed through a temp file (never
    pasted into the command line), so special characters cannot inject commands."""
    if not windows_tts_supported():
        raise SpeechSynthesisError("The built-in Windows voice is only available on Windows.")
    sapi_rate = int(round((rate - 1.0) * 10))  # 1.0 -> 0, 1.5 -> 5, 0.5 -> -5
    with tempfile.TemporaryDirectory() as tmp:
        in_path, out_path = Path(tmp) / "in.txt", Path(tmp) / "out.wav"
        in_path.write_text(text, encoding="utf-8")
        env = dict(os.environ, LINGUAAI_TTS_IN=str(in_path), LINGUAAI_TTS_OUT=str(out_path),
                   LINGUAAI_TTS_RATE=str(max(-10, min(10, sapi_rate))))
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT],
                env=env, capture_output=True, text=True, timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SpeechSynthesisError(f"Windows voice failed: {exc}") from exc
        if proc.returncode != 0 or not out_path.is_file():
            raise SpeechSynthesisError(f"Windows voice failed: {proc.stderr.strip()[:300]}")
        return out_path.read_bytes()
