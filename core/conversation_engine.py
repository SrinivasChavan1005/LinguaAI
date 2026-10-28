"""
The conversation engine: keeps the dialogue and asks the language model for replies.

How the language model receives context
---------------------------------------
Every request contains:
1. A *system* message describing the AI's role (built from the mode, scenario,
   your level and preferred English variety - see ``config/prompts.py``).
2. Only the last ``context_turns`` messages of the conversation. Older messages
   are dropped from the request (they stay on screen and in the database).
   This keeps requests small, fast and memory-friendly.

The engine has no Streamlit code, so it can be tested on its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from config.prompts import MODES, build_system_prompt, opening_line
from core.llm_client import LLMError, OllamaClient
from database import repository
from utils.logging_config import redact

logger = logging.getLogger(__name__)


@dataclass
class Message:
    role: str              # "user" or "assistant"
    text: str
    turn_id: int | None = None
    metrics: dict = field(default_factory=dict)
    input_type: str = "voice"


class ConversationEngine:
    def __init__(self, client: OllamaClient, *, mode: str, scenario: str, proficiency: str = "Intermediate",
                 variety: str = "American", context_turns: int = 8, max_reply_tokens: int = 220,
                 save_history: bool = True, db_path=None):
        if mode not in MODES:
            raise ValueError(f"Unknown conversation mode {mode!r}")
        self.client = client
        self.mode = mode
        self.scenario = scenario
        self.proficiency = proficiency
        self.variety = variety
        self.context_turns = context_turns
        self.max_reply_tokens = max_reply_tokens
        self.save_history = save_history
        self.db_path = db_path
        self.messages: list[Message] = []
        self.session_id: int | None = None
        self.ended = False

    # ------------------------------------------------------------- lifecycle
    def start(self) -> Message:
        """Begin the session with a fixed opening line (no model call needed)."""
        if self.save_history:
            self.session_id = repository.create_session(self.mode, self.scenario, db_path=self.db_path)
        opening = Message("assistant", opening_line(self.mode, self.scenario))
        self._store(opening)
        self.messages.append(opening)
        return opening

    def end(self) -> None:
        if self.session_id is not None and not self.ended:
            repository.end_session(self.session_id, db_path=self.db_path)
        self.ended = True

    @property
    def user_messages(self) -> list[Message]:
        return [m for m in self.messages if m.role == "user"]

    # ------------------------------------------------------------- dialogue
    def build_llm_messages(self) -> list[dict[str, str]]:
        system = build_system_prompt(self.mode, self.scenario, self.proficiency, self.variety)
        recent = self.messages[-self.context_turns:]
        # Most chat models expect the first non-system message to be from the user;
        # if trimming left an assistant message first, that's still accepted by Ollama.
        return [{"role": "system", "content": system}] + [
            {"role": m.role, "content": m.text} for m in recent
        ]

    def add_user_message(self, text: str, metrics: dict | None = None, input_type: str = "voice") -> Message:
        text = (text or "").strip()
        if not text:
            raise ValueError("Empty message")
        msg = Message("user", text[:4000], metrics=metrics or {}, input_type=input_type)
        self._store(msg)
        self.messages.append(msg)
        logger.info("User message %s (%s)", redact(text), input_type)
        return msg

    def generate_reply(self) -> Message:
        """Ask the model for the next reply. Raises LLMError (message is user-friendly)."""
        if not self.messages or self.messages[-1].role != "user":
            raise ValueError("generate_reply() needs a user message first")
        text = self.client.chat(self.build_llm_messages(), max_tokens=self.max_reply_tokens)
        text = text.strip()
        if not text:
            raise LLMError("The language model returned an empty reply. Please try again.")
        reply = Message("assistant", text)
        self._store(reply)
        self.messages.append(reply)
        return reply

    def previous_assistant_text(self, user_msg: Message) -> str:
        """The assistant message right before a user message (used as context for grammar checks)."""
        idx = self.messages.index(user_msg)
        for m in reversed(self.messages[:idx]):
            if m.role == "assistant":
                return m.text
        return ""

    def transcript(self, max_chars: int = 6000) -> str:
        lines = [f"{'Learner' if m.role == 'user' else 'AI'}: {m.text}" for m in self.messages]
        text = "\n".join(lines)
        return text[-max_chars:]

    # --------------------------------------------------------------- storage
    def _store(self, msg: Message) -> None:
        if self.session_id is None:
            return
        msg.turn_id = repository.add_turn(self.session_id, msg.role, msg.text, input_type=msg.input_type,
                                          metrics=msg.metrics if msg.role == "user" else None,
                                          db_path=self.db_path)
