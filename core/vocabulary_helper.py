"""
Vocabulary lookups using the local language model.

The model returns a JSON description of a word (definition, example ...).
Saved words are stored in SQLite and work without the model afterwards.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from config.prompts import VOCAB_SYSTEM_PROMPT
from core.llm_client import LLMError, OllamaClient
from utils.validators import as_str, as_str_list, clean_word, extract_json_object


@dataclass
class WordEntry:
    word: str
    definition: str = ""
    example: str = ""
    synonyms: list[str] = field(default_factory=list)
    usage: str = ""
    register: str = ""
    collocations: list[str] = field(default_factory=list)
    practice_question: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class VocabularyLookupError(Exception):
    pass


def parse_word_entry(word: str, raw: str | None) -> WordEntry:
    data = extract_json_object(raw)
    if data is None:
        raise VocabularyLookupError("The AI's answer could not be read. Please try again.")
    entry = WordEntry(
        word=word,
        definition=as_str(data.get("definition")),
        example=as_str(data.get("example")),
        synonyms=as_str_list(data.get("synonyms")),
        usage=as_str(data.get("usage")),
        register=as_str(data.get("register")).lower()[:20],
        collocations=as_str_list(data.get("collocations")),
        practice_question=as_str(data.get("practice_question")),
    )
    if not entry.definition:
        raise VocabularyLookupError("The AI did not return a definition. Please try again.")
    return entry


def lookup_word(client: OllamaClient, word: str, variety: str = "American",
                proficiency: str = "Intermediate") -> WordEntry:
    word = clean_word(word)  # raises ValueError with a friendly message
    messages = [
        {"role": "system", "content": VOCAB_SYSTEM_PROMPT.format(variety=variety, proficiency=proficiency)},
        {"role": "user", "content": f"Word or phrase: {word}"},
    ]
    try:
        raw = client.chat(messages, json_mode=True, max_tokens=400, temperature=0.2)
    except LLMError as exc:
        raise VocabularyLookupError(str(exc)) from exc
    return parse_word_entry(word, raw)
