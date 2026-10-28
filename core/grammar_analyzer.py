"""
Grammar and communication feedback using the local language model.

The model is asked to answer in JSON. Local models are not perfect, so
``parse_grammar_response`` validates every field and *never* crashes: if the
output is unusable we return a feedback object with ``ok=False`` and a
friendly message instead.

Important: corrections come from an AI model and can be wrong. The UI labels
them as suggestions and lets the user mark them as wrong or dismiss them.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from config.prompts import GRAMMAR_CATEGORIES, GRAMMAR_SYSTEM_PROMPT, GRAMMAR_USER_TEMPLATE
from core.llm_client import LLMError, OllamaClient
from utils.validators import as_bool, as_str, as_str_list, extract_json_object

logger = logging.getLogger(__name__)


@dataclass
class GrammarIssue:
    category: str
    original: str
    suggestion: str
    explanation: str

    @property
    def category_label(self) -> str:
        return GRAMMAR_CATEGORIES.get(self.category, "Other")


@dataclass
class GrammarFeedback:
    original: str
    ok: bool = True                 # False = feedback could not be produced
    has_issues: bool = False
    corrected: str = ""
    issues: list[GrammarIssue] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    practice: str = ""
    repeat_after_me: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GrammarFeedback":
        issues = [GrammarIssue(**i) for i in data.get("issues", []) if isinstance(i, dict)]
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k != "issues"}
        return cls(**known, issues=issues)

    @property
    def real_error_categories(self) -> list[str]:
        """Categories that count as mistakes (informal-but-OK is not a mistake)."""
        return [i.category for i in self.issues if i.category != "informal_ok"]


def _normalize_category(value: str) -> str:
    value = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if value in GRAMMAR_CATEGORIES:
        return value
    aliases = {"tense": "grammar", "verb": "grammar", "article": "grammar", "preposition": "grammar",
               "vocabulary": "word_choice", "word": "word_choice", "informal": "informal_ok",
               "style": "awkward", "naturalness": "unnatural", "register": "inappropriate"}
    for key, cat in aliases.items():
        if key in value:
            return cat
    return "grammar"


def parse_grammar_response(original: str, raw: str | None) -> GrammarFeedback:
    """Turn raw model output into a validated GrammarFeedback. Never raises."""
    data = extract_json_object(raw)
    if data is None:
        logger.warning("Grammar model output was not valid JSON (%d chars)", len(raw or ""))
        return GrammarFeedback(original=original, ok=False,
                               error="The AI's feedback could not be read this time. Try 'Check again'.")

    issues: list[GrammarIssue] = []
    raw_issues = data.get("issues")
    if isinstance(raw_issues, list):
        for item in raw_issues[:6]:
            if not isinstance(item, dict):
                continue
            issue = GrammarIssue(
                category=_normalize_category(as_str(item.get("category"))),
                original=as_str(item.get("original")),
                suggestion=as_str(item.get("suggestion")),
                explanation=as_str(item.get("explanation")),
            )
            if issue.original or issue.suggestion or issue.explanation:
                issues.append(issue)

    corrected = as_str(data.get("corrected"), default=original)
    has_issues = as_bool(data.get("has_issues"), default=bool(issues))
    # Keep the result self-consistent.
    if issues and not any(i.category != "informal_ok" for i in issues):
        has_issues = False
    elif issues:
        has_issues = True
    if not has_issues and not issues:
        corrected = corrected or original

    return GrammarFeedback(
        original=original,
        ok=True,
        has_issues=has_issues,
        corrected=corrected,
        issues=issues,
        alternatives=[a for a in as_str_list(data.get("alternatives"), max_items=3)
                      if a.strip().lower() != corrected.strip().lower()],
        practice=as_str(data.get("practice")),
        repeat_after_me=as_str(data.get("repeat_after_me"), default=corrected, max_len=250),
    )


class GrammarAnalyzer:
    def __init__(self, client: OllamaClient, variety: str = "American", proficiency: str = "Intermediate"):
        self.client = client
        self.variety = variety
        self.proficiency = proficiency

    def analyze(self, text: str, context: str = "") -> GrammarFeedback:
        text = (text or "").strip()
        if not text:
            return GrammarFeedback(original="", ok=False, error="There is no speech to check.")
        if len(text.split()) < 2:
            return GrammarFeedback(original=text, ok=True, has_issues=False, corrected=text,
                                   error="Very short answer - nothing to check.")
        messages = [
            {"role": "system", "content": GRAMMAR_SYSTEM_PROMPT.format(
                variety=self.variety, proficiency=self.proficiency)},
            {"role": "user", "content": GRAMMAR_USER_TEMPLATE.format(
                context=context[:400] or "free conversation", text=text[:1500])},
        ]
        try:
            raw = self.client.chat(messages, json_mode=True, max_tokens=450, temperature=0.2)
        except LLMError as exc:
            return GrammarFeedback(original=text, ok=False, error=str(exc))
        return parse_grammar_response(text, raw)
