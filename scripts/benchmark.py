"""
Measure the speed of each local component on YOUR computer (no microphone needed).

    venv\\Scripts\\python scripts\\benchmark.py

1. Text-to-speech: speak a test sentence.
2. Speech recognition: transcribe that generated audio (load time + speed).
3. Language model: one short reply.
4. Memory used by this process and by Ollama.

Results are printed and appended to logs/benchmark.log so you can compare
models later.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from audio.audio_utils import decode_wav  # noqa: E402
from config.settings import LOGS_DIR, AppSettings  # noqa: E402
from core.llm_client import LLMError, OllamaClient  # noqa: E402
from core.performance_monitor import ollama_process_memory_mb, process_memory_mb  # noqa: E402
from core.speech_recognition import SpeechRecognitionError, SpeechRecognizer  # noqa: E402
from core.speech_synthesis import SpeechSynthesisError, SpeechSynthesizer  # noqa: E402

SENTENCE = "Yesterday I went to college and met my friend. We talked about our final project."


def main() -> int:
    s = AppSettings.load()
    lines = [f"--- {datetime.now():%Y-%m-%d %H:%M} whisper={s.whisper_model} llm={s.ollama_model} "
             f"tts={s.tts_engine}:{s.piper_voice}"]

    def report(text: str) -> None:
        print(text)
        lines.append(text)

    wav = None
    try:
        wav, secs = SpeechSynthesizer(s).synthesize(SENTENCE)
        report(f"[ok] TTS: {secs:.2f}s to generate {len(wav) / 32000:.1f}s of speech")
    except SpeechSynthesisError as exc:
        report(f"[!!] TTS failed: {exc}")

    if wav:
        rec = SpeechRecognizer(s)
        try:
            rec.load()
            report(f"[ok] Whisper load: {rec.load_seconds:.2f}s on {rec.device_used}"
                   + (f" ({rec.notice})" if rec.notice else ""))
            result = rec.transcribe(decode_wav(wav))
            report(f"[ok] Whisper: {result.processing_seconds:.2f}s for {result.audio_duration:.1f}s audio")
            report(f"     Heard: {result.text}")
        except SpeechRecognitionError as exc:
            report(f"[!!] Speech recognition failed: {exc}")
    else:
        report("[--] Skipped speech recognition test (needs TTS audio).")

    client = OllamaClient(s)
    try:
        t = time.perf_counter()
        client.chat([{"role": "user", "content": "Reply with one friendly sentence."}], max_tokens=40)
        first = time.perf_counter() - t
        t = time.perf_counter()
        reply = client.chat([{"role": "user", "content": "Ask me one question about my hobbies."}], max_tokens=60)
        second = time.perf_counter() - t
        report(f"[ok] LLM: first call {first:.2f}s (includes loading), second call {second:.2f}s")
        report(f"     Reply: {reply}")
    except LLMError as exc:
        report(f"[!!] Language model failed: {exc}")

    report(f"     Memory: LinguaAI process {process_memory_mb()} MB, Ollama {ollama_process_memory_mb()} MB")
    LOGS_DIR.mkdir(exist_ok=True)
    with open(LOGS_DIR / "benchmark.log", "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
