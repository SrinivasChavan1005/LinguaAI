"""
Local speech recognition with Faster-Whisper.

* The model is loaded once ("lazy loading": only when first needed) and then
  kept in memory, so we do not reload it for every sentence.
* Models are read ONLY from ``models/whisper/<name>/``. We never download
  during normal use. ``scripts/download_models.py`` prepares them once.
* GPU (CUDA) is used only when it is available AND actually loads; otherwise
  CPU is used and the user is told why.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from config.settings import WHISPER_MODELS_DIR, AppSettings

logger = logging.getLogger(__name__)

# This prompt nudges Whisper to keep filler words ("um", "uh") in the
# transcript. Without it Whisper usually deletes them, which would make the
# filler-word statistics meaningless.
FILLER_PROMPT = "Umm, let me think like, hmm... Okay, here's what I'm, like, thinking."


class SpeechRecognitionError(Exception):
    """Base error; ``str(err)`` is a user-friendly message."""


class ModelMissingError(SpeechRecognitionError):
    pass


@dataclass
class WordTiming:
    word: str
    start: float
    end: float
    probability: float


@dataclass
class TranscriptResult:
    text: str
    words: list[WordTiming] = field(default_factory=list)
    audio_duration: float = 0.0
    speech_segments: list[tuple[float, float]] = field(default_factory=list)  # from VAD
    processing_seconds: float = 0.0
    language_probability: float | None = None

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


def whisper_model_dir(model_name: str) -> Path:
    """Folder where a Whisper model is expected. A full path is also accepted."""
    path = Path(model_name)
    if path.is_absolute() or path.is_dir():
        return path
    return WHISPER_MODELS_DIR / model_name


def whisper_model_available(model_name: str) -> bool:
    folder = whisper_model_dir(model_name)
    return (folder / "model.bin").is_file() and (folder / "config.json").is_file()


def cuda_device_count() -> int:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception as exc:  # ctranslate2 raises various errors without a GPU driver
        logger.info("CUDA check failed: %s", exc)
        return 0


def detect_speech_segments(audio: np.ndarray, sample_rate: int = 16_000) -> list[tuple[float, float]]:
    """Voice activity detection using the small Silero VAD model bundled with
    faster-whisper (no download needed). Returns (start, end) in seconds."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    if audio.size == 0:
        return []
    stamps = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=300), sampling_rate=sample_rate)
    return [(s["start"] / sample_rate, s["end"] / sample_rate) for s in stamps]


class SpeechRecognizer:
    """Wraps a Faster-Whisper model. Create once, reuse for every recording."""

    def __init__(self, settings: AppSettings):
        self.model_name = settings.whisper_model
        self.requested_device = settings.whisper_device
        self.compute_type = settings.whisper_compute_type
        self.beam_size = settings.whisper_beam_size
        self.keep_fillers = settings.keep_filler_words
        self._model = None
        self._lock = threading.Lock()  # Streamlit may run two reruns at once
        self.device_used: str | None = None
        self.notice: str | None = None   # e.g. "CUDA failed, using CPU"
        self.load_seconds: float | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Load the model if it is not loaded yet."""
        with self._lock:
            if self._model is not None:
                return
            folder = whisper_model_dir(self.model_name)
            if not whisper_model_available(self.model_name):
                raise ModelMissingError(
                    f"Speech recognition model '{self.model_name}' was not found in {folder}. "
                    "Run setup_linguaai.bat (or: python scripts\\download_models.py) once while "
                    "connected to the internet."
                )
            from faster_whisper import WhisperModel

            device = self.requested_device
            if device == "auto":
                device = "cuda" if cuda_device_count() > 0 else "cpu"
            compute = self.compute_type
            if device == "cpu" and compute in ("float16", "int8_float16"):
                self.notice = f"Compute type '{compute}' is not supported on CPU; using 'int8'."
                compute = "int8"

            started = time.perf_counter()
            try:
                self._model = WhisperModel(str(folder), device=device, compute_type=compute,
                                           local_files_only=True)
                self.device_used = device
            except (RuntimeError, ValueError, OSError) as exc:
                if device == "cuda":
                    # Common on Windows when CUDA/cuDNN libraries are missing.
                    logger.warning("CUDA load failed (%s); falling back to CPU", exc)
                    self.notice = ("GPU (CUDA) could not be used, so speech recognition runs on the "
                                   f"CPU instead. Reason: {str(exc)[:160]}")
                    try:
                        self._model = WhisperModel(str(folder), device="cpu", compute_type="int8",
                                                   local_files_only=True)
                        self.device_used = "cpu"
                    except (RuntimeError, ValueError, OSError) as exc2:
                        raise SpeechRecognitionError(_load_error_message(exc2, folder)) from exc2
                else:
                    raise SpeechRecognitionError(_load_error_message(exc, folder)) from exc
            self.load_seconds = time.perf_counter() - started
            logger.info("Whisper '%s' loaded on %s in %.1fs", self.model_name, self.device_used,
                        self.load_seconds)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16_000) -> TranscriptResult:
        """Transcribe mono float32 16 kHz audio."""
        duration = audio.size / sample_rate if sample_rate else 0.0
        if audio.size == 0:
            return TranscriptResult(text="", audio_duration=0.0)
        self.load()
        started = time.perf_counter()
        segments_vad = detect_speech_segments(audio, sample_rate)
        if not segments_vad:
            return TranscriptResult(text="", audio_duration=duration,
                                    processing_seconds=time.perf_counter() - started)
        try:
            with self._lock:
                segments, info = self._model.transcribe(
                    audio,
                    language="en",
                    beam_size=self.beam_size,
                    word_timestamps=True,
                    vad_filter=True,
                    condition_on_previous_text=False,
                    initial_prompt=FILLER_PROMPT if self.keep_fillers else None,
                )
                segments = list(segments)  # transcription actually happens here
        except (RuntimeError, ValueError, MemoryError) as exc:
            raise SpeechRecognitionError(f"Speech recognition failed: {exc}") from exc

        words: list[WordTiming] = []
        texts: list[str] = []
        for seg in segments:
            texts.append(seg.text.strip())
            for w in seg.words or []:
                words.append(WordTiming(w.word.strip(), float(w.start), float(w.end), float(w.probability)))
        text = " ".join(t for t in texts if t).strip()
        elapsed = time.perf_counter() - started
        logger.info("Transcribed %.1fs of audio in %.2fs (%d words)", duration, elapsed, len(words))
        return TranscriptResult(
            text=text, words=words, audio_duration=duration, speech_segments=segments_vad,
            processing_seconds=elapsed, language_probability=getattr(info, "language_probability", None),
        )


def _load_error_message(exc: Exception, folder: Path) -> str:
    text = str(exc)
    if "memory" in text.lower() or isinstance(exc, MemoryError):
        return ("Not enough memory to load the speech recognition model. Choose 'tiny.en' in "
                "Settings or close other programs.")
    return (f"Could not load the speech recognition model from {folder}. The files may be "
            f"incomplete or corrupted - delete that folder and run setup again. Details: {text[:200]}")
