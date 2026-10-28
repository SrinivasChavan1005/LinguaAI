"""
Pronunciation practice: compare what you were asked to say with what the
speech recogniser heard.

What this CAN tell you
* Which reference words were missing, or heard as a different word.
* Which words the recogniser was unsure about (low word probability).
* Your speaking duration and basic audio quality.

What this CANNOT tell you
* It does not measure individual sounds (phonemes). A word can be
  recognised correctly while still sounding accented, and a correct word can
  be mis-recognised because of noise or the microphone. That is why the
  result is called "transcript match", not "pronunciation score".
  (Phoneme-level scoring needs extra models such as wav2vec2 phoneme
  recognisers, which require PyTorch, ~1-2 GB extra disk and more RAM than
  is comfortable on an 8 GB laptop. See docs/DEVELOPMENT_GUIDE.md.)
"""

from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass, field

from core.speech_recognition import WordTiming
from utils.validators import normalize_words

LOW_CONFIDENCE = 0.5

# Simple spelling-based hints linking difficult words to practice sets.
# These are heuristics based on the spelling, not on measured sounds.
SOUND_HINTS = [
    ("th", "th", "TH sounds (think / this)"),
    ("v", "v_w", "V and W sounds (very / west)"),
    ("w", "v_w", "V and W sounds (very / west)"),
    ("r", "r_l", "R and L sounds (right / light)"),
    ("l", "r_l", "R and L sounds (right / light)"),
    ("ed", "endings", "Word endings (-ed, -s)"),
    ("s", "endings", "Word endings (-ed, -s)"),
]


@dataclass
class WordResult:
    reference: str            # word you were asked to say ("" for extra words)
    heard: str                # word that was recognised ("" if missing)
    status: str               # "match", "different", "missing", "extra"
    probability: float | None = None

    @property
    def unsure(self) -> bool:
        return self.probability is not None and self.probability < LOW_CONFIDENCE


@dataclass
class PronunciationResult:
    reference_text: str
    recognized_text: str
    words: list[WordResult] = field(default_factory=list)
    transcript_match: float = 0.0     # share of reference words recognised exactly (0..1)
    missing: list[str] = field(default_factory=list)
    different: list[tuple[str, str]] = field(default_factory=list)
    unsure: list[str] = field(default_factory=list)
    practice_tags: list[tuple[str, str]] = field(default_factory=list)  # (tag, label)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["words"] = [asdict(w) for w in self.words]
        return d


def compare_transcript(reference: str, recognized: str,
                       word_timings: list[WordTiming] | None = None) -> PronunciationResult:
    """Align reference and recognised words with difflib (no AI involved)."""
    ref = normalize_words(reference)
    hyp = normalize_words(recognized)
    # Map recognised word index -> Whisper probability (same order as the transcript).
    probs: list[float | None] = [None] * len(hyp)
    if word_timings:
        timing_tokens: list[tuple[str, float]] = []
        for wt in word_timings:
            for tok in normalize_words(wt.word):
                timing_tokens.append((tok, wt.probability))
        if [t for t, _ in timing_tokens] == hyp:
            probs = [p for _, p in timing_tokens]

    result = PronunciationResult(reference_text=reference, recognized_text=recognized)
    matcher = difflib.SequenceMatcher(a=ref, b=hyp, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                result.words.append(WordResult(ref[i1 + k], hyp[j1 + k], "match", probs[j1 + k]))
        elif op == "replace":
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                r = ref[i1 + k] if i1 + k < i2 else ""
                h = hyp[j1 + k] if j1 + k < j2 else ""
                p = probs[j1 + k] if j1 + k < j2 else None
                status = "different" if r and h else ("missing" if r else "extra")
                result.words.append(WordResult(r, h, status, p))
        elif op == "delete":
            for k in range(i1, i2):
                result.words.append(WordResult(ref[k], "", "missing"))
        elif op == "insert":
            for k in range(j1, j2):
                result.words.append(WordResult("", hyp[k], "extra", probs[k]))

    matches = sum(1 for w in result.words if w.status == "match")
    result.transcript_match = round(matches / len(ref), 3) if ref else 0.0
    result.missing = [w.reference for w in result.words if w.status == "missing"]
    result.different = [(w.reference, w.heard) for w in result.words if w.status == "different"]
    result.unsure = [w.heard for w in result.words if w.status == "match" and w.unsure]

    difficult = result.missing + [r for r, _ in result.different] + result.unsure
    seen: set[str] = set()
    for word in difficult:
        for pattern, tag, label in SOUND_HINTS:
            hit = word.endswith(pattern) if tag == "endings" else pattern in word
            if hit and tag not in seen:
                seen.add(tag)
                result.practice_tags.append((tag, label))
    return result
