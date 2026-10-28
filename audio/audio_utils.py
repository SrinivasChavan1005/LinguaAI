"""
Audio helpers: turn the browser recording into numbers and check its quality.

How audio travels through LinguaAI
----------------------------------
1. You press the microphone button in the page. Your *browser* records audio
   (it shows its own red recording indicator and asks for permission once).
2. When you press stop, the browser sends a WAV file (16 kHz) to the local
   Streamlit server on 127.0.0.1 - it never leaves your computer.
3. ``decode_wav`` converts the WAV bytes into a NumPy array of floats between
   -1.0 and 1.0, mono, 16 000 samples per second (what Whisper expects).
4. ``analyze_quality`` measures loudness, clipping and silence so we can warn
   about empty or too-quiet recordings *before* running speech recognition.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

TARGET_SAMPLE_RATE = 16_000


class AudioError(Exception):
    """Raised when audio cannot be read. The message is shown to the user."""


@dataclass
class AudioQuality:
    duration_s: float
    rms_dbfs: float          # average loudness; around -20 dBFS is comfortable
    peak: float              # 0..1
    clipping_ratio: float    # share of samples at maximum level (distortion)
    voiced_ratio: float      # share of 30 ms frames louder than the silence threshold
    is_silent: bool
    warnings: list[str]


def decode_wav(data: bytes) -> np.ndarray:
    """Decode WAV bytes to mono float32 at 16 kHz."""
    if not data:
        raise AudioError("The recording is empty. Please try recording again.")
    try:
        rate, samples = wavfile.read(io.BytesIO(data))
    except (ValueError, OSError, EOFError) as exc:
        raise AudioError("Could not read the recording (it is not a valid WAV file).") from exc

    samples = _to_float32(samples)
    if samples.ndim == 2:  # stereo -> mono
        samples = samples.mean(axis=1)
    if samples.size == 0:
        raise AudioError("The recording is empty. Please try recording again.")
    if rate != TARGET_SAMPLE_RATE:
        from math import gcd

        g = gcd(int(rate), TARGET_SAMPLE_RATE)
        samples = resample_poly(samples, TARGET_SAMPLE_RATE // g, int(rate) // g).astype(np.float32)
    return np.clip(samples, -1.0, 1.0).astype(np.float32)


def _to_float32(samples: np.ndarray) -> np.ndarray:
    if samples.dtype == np.int16:
        return samples.astype(np.float32) / 32768.0
    if samples.dtype == np.int32:
        return samples.astype(np.float32) / 2147483648.0
    if samples.dtype == np.uint8:
        return (samples.astype(np.float32) - 128.0) / 128.0
    return samples.astype(np.float32)


def analyze_quality(audio: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE,
                    silence_dbfs: float = -45.0) -> AudioQuality:
    """Basic, honest audio-quality indicators (no AI involved)."""
    duration = float(audio.size) / sample_rate if sample_rate else 0.0
    if audio.size == 0:
        return AudioQuality(0.0, -120.0, 0.0, 0.0, 0.0, True, ["The recording is empty."])

    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    rms_dbfs = 20 * np.log10(max(rms, 1e-6))
    peak = float(np.max(np.abs(audio)))
    clipping = float(np.mean(np.abs(audio) >= 0.99))

    frame = int(0.03 * sample_rate)
    n_frames = max(1, audio.size // frame)
    frames = audio[: n_frames * frame].reshape(n_frames, -1) if audio.size >= frame else audio[None, :]
    frame_db = 20 * np.log10(np.maximum(np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1)), 1e-6))
    voiced_ratio = float(np.mean(frame_db > silence_dbfs))
    is_silent = voiced_ratio < 0.02 or peak < 0.01

    warnings = []
    if is_silent:
        warnings.append("No speech was detected. Check that the right microphone is selected "
                        "in your browser and that it is not muted.")
    elif rms_dbfs < -40:
        warnings.append("The recording is very quiet. Move closer to the microphone.")
    if clipping > 0.01:
        warnings.append("The recording is distorted (too loud). Move a little away from the microphone.")
    return AudioQuality(round(duration, 2), round(float(rms_dbfs), 1), round(peak, 3),
                        round(clipping, 4), round(voiced_ratio, 3), is_silent, warnings)


def float_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Encode mono float audio as 16-bit WAV bytes (for playback in the browser)."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def wav_duration(data: bytes) -> float:
    """Duration of WAV bytes in seconds (0.0 if unreadable)."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except (wave.Error, EOFError, ZeroDivisionError):
        return 0.0
