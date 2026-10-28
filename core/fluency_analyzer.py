"""
Fluency metrics calculated from the transcript and word timings.

These are *measurements*, not judgements. Their limits (also shown in the UI):

* Speaking time = time between words, with pauses of 0.3 s or longer removed.
  It comes from Whisper's word timestamps, which are approximate (+/- ~0.2 s).
* Words per minute (WPM) uses speaking time, not total recording time, so
  silence at the start/end does not lower your score. Not shown for very
  short answers (< 3 s of speech) because it would be unreliable.
* Filler words: Whisper often removes "um"/"uh" from transcripts. We ask it
  to keep them, but some will still be missed, so counts are a minimum.
  "like" is NOT counted because it is usually a normal word.
* Long pause = gap between two words longer than the threshold (default 1 s).
  Pauses are normal in speech; this is information, not an error count.
* Repeated words = the same word twice in a row ("I I think"). Some
  repetitions are intentional ("very very"), so treat this as a hint.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from core.speech_recognition import WordTiming
from utils.validators import normalize_words

SINGLE_FILLERS = {"um", "umm", "uh", "uhh", "er", "erm", "ah", "hmm", "mm", "eh"}
PHRASE_FILLERS = ("you know", "i mean", "sort of", "kind of")
MIN_SPEECH_FOR_WPM = 3.0
PAUSE_MERGE_GAP = 0.3


@dataclass
class FluencyMetrics:
    recording_seconds: float
    speaking_seconds: float
    word_count: int
    words_per_minute: float | None
    filler_count: int
    fillers: dict[str, int] = field(default_factory=dict)
    long_pauses: int = 0
    longest_pause: float = 0.0
    repeated_words: list[str] = field(default_factory=list)
    sentence_count: int = 0
    avg_sentence_length: float = 0.0
    continuity: float | None = None   # speaking time / time from first to last word

    def to_dict(self) -> dict:
        return asdict(self)


def merged_speech_time(words: list[WordTiming], merge_gap: float = PAUSE_MERGE_GAP) -> float:
    """Total time spent speaking: join word intervals, drop gaps >= merge_gap."""
    if not words:
        return 0.0
    ordered = sorted(words, key=lambda w: w.start)
    total = 0.0
    seg_start, seg_end = ordered[0].start, ordered[0].end
    for w in ordered[1:]:
        if w.start - seg_end < merge_gap:
            seg_end = max(seg_end, w.end)
        else:
            total += seg_end - seg_start
            seg_start, seg_end = w.start, w.end
    total += seg_end - seg_start
    return max(total, 0.0)


def count_fillers(text: str) -> dict[str, int]:
    tokens = normalize_words(text)
    counts: dict[str, int] = {}
    for tok in tokens:
        if tok in SINGLE_FILLERS:
            key = "um" if tok.startswith("um") else "uh" if tok.startswith("uh") else tok
            counts[key] = counts.get(key, 0) + 1
    joined = " " + " ".join(tokens) + " "
    for phrase in PHRASE_FILLERS:
        n = joined.count(f" {phrase} ")
        if n:
            counts[phrase] = n
    return counts


def find_repeated_words(text: str) -> list[str]:
    tokens = normalize_words(text)
    repeats = []
    for a, b in zip(tokens, tokens[1:]):
        if a == b and a not in SINGLE_FILLERS and a not in ("very", "really", "so", "no", "bye", "ha"):
            repeats.append(a)
    return repeats


def sentence_stats(text: str) -> tuple[int, float]:
    parts = [p for p in re.split(r"[.!?]+", text) if p.strip()]
    if not parts:
        return 0, 0.0
    lengths = [len(normalize_words(p)) for p in parts]
    lengths = [n for n in lengths if n > 0]
    if not lengths:
        return 0, 0.0
    return len(lengths), round(sum(lengths) / len(lengths), 1)


def analyze_fluency(text: str, words: list[WordTiming], recording_seconds: float,
                    long_pause_seconds: float = 1.0) -> FluencyMetrics:
    """Compute fluency metrics. Works with an empty transcript (returns zeros)."""
    text = text or ""
    tokens = normalize_words(text)
    fillers = count_fillers(text)
    speaking = merged_speech_time(words)
    # If word timings are missing (e.g. typed text), we cannot measure time.
    wpm = None
    if speaking >= MIN_SPEECH_FOR_WPM:
        wpm = round(len(tokens) / speaking * 60, 1)

    long_pauses, longest = 0, 0.0
    ordered = sorted(words, key=lambda w: w.start)
    for prev, cur in zip(ordered, ordered[1:]):
        gap = cur.start - prev.end
        longest = max(longest, gap)
        if gap >= long_pause_seconds:
            long_pauses += 1

    continuity = None
    if len(ordered) >= 2:
        span = ordered[-1].end - ordered[0].start
        if span > 0:
            continuity = round(min(speaking / span, 1.0), 2)

    n_sent, avg_len = sentence_stats(text)
    return FluencyMetrics(
        recording_seconds=round(recording_seconds, 2),
        speaking_seconds=round(speaking, 2),
        word_count=len(tokens),
        words_per_minute=wpm,
        filler_count=sum(fillers.values()),
        fillers=fillers,
        long_pauses=long_pauses,
        longest_pause=round(max(longest, 0.0), 2),
        repeated_words=find_repeated_words(text),
        sentence_count=n_sent,
        avg_sentence_length=avg_len,
        continuity=continuity,
    )


def describe_wpm(wpm: float | None) -> str:
    """Plain-language description. Typical conversational English is ~110-160 WPM."""
    if wpm is None:
        return "Not enough speech to measure speaking rate."
    if wpm < 90:
        return "Slow and careful. Fine while learning; aim for smoother phrases over time."
    if wpm <= 170:
        return "A comfortable conversational pace."
    return "Quite fast. Slowing down slightly can make you easier to understand."
