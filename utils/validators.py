"""
Small validation helpers, mainly for safely reading the language model's output.

Local language models sometimes return JSON wrapped in ```code fences```, add a
sentence before the JSON, or return broken JSON. These helpers never use
eval()/exec(); they only use the standard ``json`` parser.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json_object(text: str | None) -> dict[str, Any] | None:
    """Find and parse the first JSON object in ``text``. Returns None on failure."""
    if not text or not isinstance(text, str):
        return None
    candidates: list[str] = [text.strip()]
    candidates += [m.strip() for m in _FENCE_RE.findall(text)]
    # Fallback: the substring from the first "{" to the matching last "}".
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    return None


def as_str(value: Any, default: str = "", max_len: int = 600) -> str:
    """Coerce a model value to a clean, length-limited string."""
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return default
    text = str(value).strip()
    return text[:max_len] if text else default


def as_str_list(value: Any, max_items: int = 5, max_len: int = 300) -> list[str]:
    """Coerce a model value to a list of non-empty strings."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, (str, int, float)) and str(item).strip():
            out.append(str(item).strip()[:max_len])
        if len(out) >= max_items:
            break
    return out


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.strip().lower() in {"true", "yes", "1"}:
            return True
        if value.strip().lower() in {"false", "no", "0"}:
            return False
    return default


def clean_word(text: str, max_len: int = 60) -> str:
    """Validate a vocabulary word/phrase typed by the user."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        raise ValueError("Please type a word or short phrase.")
    if len(text) > max_len:
        raise ValueError(f"Please keep it under {max_len} characters.")
    if not re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", text):
        raise ValueError("Use English letters, spaces, hyphens or apostrophes only.")
    return text


def normalize_words(text: str) -> list[str]:
    """Lower-case word tokens without punctuation (used for comparisons)."""
    text = text.lower().replace("’", "'")
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)
