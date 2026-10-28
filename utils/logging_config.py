"""
Logging setup.

Logs go to ``logs/linguaai.log`` (rotated, max ~1 MB x 3 files) and the console.
Privacy: we log *what happened* (timings, errors, word counts), never the full
text of your conversations. Use ``redact()`` whenever user text must appear.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from config.settings import LOGS_DIR

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging once (Streamlit re-runs scripts, so guard against duplicates)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        LOGS_DIR / "linguaai.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console)
    # Quieten noisy libraries.
    for noisy in ("faster_whisper", "urllib3", "httpx", "huggingface_hub", "streamlit",
                  "watchdog", "PIL", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


def redact(text: str, keep: int = 0) -> str:
    """Return a privacy-safe description of user text for logs."""
    words = len(text.split()) if text else 0
    preview = f" '{text[:keep]}...'" if keep and text else ""
    return f"<{words} words{preview}>"
