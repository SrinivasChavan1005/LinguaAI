"""Shared test fixtures. Tests never download models or need a microphone."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """A fresh temporary database for each test."""
    from database.database import initialize

    path = tmp_path / "test.db"
    monkeypatch.setenv("LINGUAAI_DB", str(path))
    initialize(path)
    return path


class FakeLLM:
    """Stands in for OllamaClient. Returns queued replies and records requests."""

    def __init__(self, replies=None, error=None):
        self.replies = list(replies or [])
        self.error = error
        self.calls = []

    def chat(self, messages, json_mode=False, max_tokens=300, temperature=0.7):
        self.calls.append({"messages": messages, "json_mode": json_mode})
        if self.error:
            raise self.error
        return self.replies.pop(0) if self.replies else "OK."


@pytest.fixture
def fake_llm():
    return FakeLLM
