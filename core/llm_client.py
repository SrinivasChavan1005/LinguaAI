"""
Client for the local Ollama server (the "brain" of LinguaAI).

Ollama runs on your computer and listens on http://127.0.0.1:11434.
We talk to it with plain HTTP requests. Nothing is sent to the internet:
``AppSettings.validate()`` refuses any host that is not localhost.

Ollama API used:
- GET  /api/tags  -> list of installed models
- POST /api/chat  -> chat completion
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from config.settings import AppSettings, is_local_url

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base class for language-model problems. ``message`` is shown to the user."""


class OllamaNotRunningError(LLMError):
    pass


class ModelNotInstalledError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


@dataclass
class OllamaStatus:
    running: bool
    installed_models: list[str]
    model_ready: bool
    message: str


class OllamaClient:
    """Tiny wrapper around the Ollama HTTP API."""

    def __init__(self, settings: AppSettings, session: requests.Session | None = None):
        if not is_local_url(settings.ollama_host):
            raise ValueError("Ollama host must be on this computer (localhost).")
        self.host = settings.ollama_host.rstrip("/")
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout_seconds
        self.num_ctx = settings.ollama_context_tokens
        self.keep_alive = settings.ollama_keep_alive
        self.http = session or requests.Session()
        # Never pick up a system proxy for local traffic.
        self.http.trust_env = False

    # ------------------------------------------------------------------ status
    def list_models(self) -> list[str]:
        try:
            resp = self.http.get(f"{self.host}/api/tags", timeout=3)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise OllamaNotRunningError(
                "Ollama is not running. Start the Ollama app (or run 'ollama serve' in a terminal)."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise LLMError(f"Could not talk to Ollama: {exc}") from exc
        data = resp.json() if resp.content else {}
        return sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))

    def status(self) -> OllamaStatus:
        try:
            models = self.list_models()
        except LLMError as exc:
            return OllamaStatus(False, [], False, str(exc))
        ready = model_is_installed(self.model, models)
        msg = (f"Model '{self.model}' is ready." if ready else
               f"Model '{self.model}' is not installed. Run: ollama pull {self.model}")
        return OllamaStatus(True, models, ready, msg)

    # -------------------------------------------------------------------- chat
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        max_tokens: int = 300,
        temperature: float = 0.7,
    ) -> str:
        """Send chat messages and return the assistant's text. Raises LLMError subclasses."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if json_mode:
            payload["format"] = "json"
        started = time.perf_counter()
        try:
            resp = self.http.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
        except requests.exceptions.ConnectionError as exc:
            raise OllamaNotRunningError(
                "Lost connection to Ollama. Make sure the Ollama app is running."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError(
                f"The language model took longer than {self.timeout}s. Try a smaller model "
                "(Settings -> Language model) or close other programs to free memory."
            ) from exc

        if resp.status_code == 404:
            raise ModelNotInstalledError(
                f"Model '{self.model}' is not installed. Open a terminal and run: ollama pull {self.model}"
            )
        if resp.status_code >= 400:
            detail = _error_detail(resp)
            if "memory" in detail.lower():
                raise LLMError(
                    f"Not enough memory to load '{self.model}'. Close other programs or choose a "
                    f"smaller model in Settings. (Ollama said: {detail})"
                )
            raise LLMError(f"Ollama returned an error ({resp.status_code}): {detail}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError("Ollama returned a response that was not valid JSON.") from exc
        content = (data.get("message") or {}).get("content", "")
        logger.info("LLM reply in %.2fs (%d chars, json=%s)",
                    time.perf_counter() - started, len(content), json_mode)
        return content.strip()


def model_is_installed(wanted: str, installed: list[str]) -> bool:
    """Ollama names look like 'llama3.2:3b'. 'llama3.2' means 'llama3.2:latest'."""
    if ":" not in wanted:
        wanted = f"{wanted}:latest"
    return wanted in installed


def _error_detail(resp: requests.Response) -> str:
    try:
        return str(resp.json().get("error", resp.text))[:300]
    except ValueError:
        return resp.text[:300]
