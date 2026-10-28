"""
Measures how long each step takes and how much memory LinguaAI uses.

Numbers are shown in Settings -> Diagnostics and under each conversation turn.
We measure instead of guessing, so you can decide whether a bigger/smaller
model is right for your laptop.
"""

from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

try:
    import psutil
except ImportError:  # psutil is in requirements, but keep diagnostics optional
    psutil = None


@dataclass
class TurnTiming:
    asr_seconds: float | None = None
    llm_seconds: float | None = None
    tts_seconds: float | None = None
    grammar_seconds: float | None = None
    total_seconds: float | None = None   # from "recording received" to "reply audio ready"
    audio_seconds: float | None = None


@dataclass
class PerformanceMonitor:
    history: deque = field(default_factory=lambda: deque(maxlen=50))
    startup_seconds: float | None = None

    def add(self, timing: TurnTiming) -> None:
        self.history.append(timing)

    def averages(self) -> dict[str, float | None]:
        out = {}
        for key in ("asr_seconds", "llm_seconds", "tts_seconds", "grammar_seconds", "total_seconds"):
            values = [getattr(t, key) for t in self.history if getattr(t, key) is not None]
            out[key] = round(sum(values) / len(values), 2) if values else None
        return out


class Stopwatch:
    def __init__(self):
        self.seconds: float | None = None


@contextmanager
def timed() -> Iterator[Stopwatch]:
    """``with timed() as t: ...`` then read ``t.seconds``."""
    sw = Stopwatch()
    start = time.perf_counter()
    try:
        yield sw
    finally:
        sw.seconds = round(time.perf_counter() - start, 3)


def process_memory_mb() -> float | None:
    """Memory used by the LinguaAI Python process (Whisper + Piper live here)."""
    if psutil is None:
        return None
    return round(psutil.Process().memory_info().rss / 1_048_576, 1)


def system_memory() -> dict[str, float] | None:
    if psutil is None:
        return None
    vm = psutil.virtual_memory()
    return {"total_gb": round(vm.total / 1e9, 1), "available_gb": round(vm.available / 1e9, 1),
            "percent_used": vm.percent}


def ollama_process_memory_mb() -> float | None:
    """Ollama runs as a separate program; sum the memory of its processes."""
    if psutil is None:
        return None
    total = 0
    found = False
    for proc in psutil.process_iter(["name", "memory_info"]):
        name = (proc.info.get("name") or "").lower()
        if name.startswith("ollama"):
            found = True
            mem = proc.info.get("memory_info")
            total += mem.rss if mem else 0
    return round(total / 1_048_576, 1) if found else None
