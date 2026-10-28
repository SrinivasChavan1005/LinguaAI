"""
All instructions ("prompts") sent to the local language model live here.

Keeping prompts in one file makes it easy to read exactly what the AI is told
and to improve the wording without touching application logic.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Conversation modes and scenarios
# ---------------------------------------------------------------------------
MODES: dict[str, dict] = {
    "daily": {
        "label": "Daily English conversation",
        "icon": ":material/chat:",
        "scenarios": ["Family", "Friends", "Hobbies", "College", "Technology", "Sports",
                      "Travel", "Everyday activities", "Current interests"],
        "instruction": (
            "Have a relaxed, friendly conversation about the topic: {scenario}. "
            "Ask exactly ONE natural follow-up question at a time."
        ),
        "opening": "Let's chat about {scenario_lower}. What would you like to tell me first?",
    },
    "interview": {
        "label": "Job interview practice",
        "icon": ":material/work:",
        "scenarios": ["Self-introduction", "Tell me about yourself", "Strengths and weaknesses",
                      "Project explanation", "Career goals", "HR questions",
                      "Behavioural questions (STAR)", "Technical interview communication",
                      "Questions to ask the interviewer"],
        "instruction": (
            "You are a professional but kind job interviewer. Focus on: {scenario}. "
            "Ask one interview question at a time, then a short, realistic follow-up based "
            "on the candidate's answer. Stay in the interviewer role. Do NOT judge technical "
            "correctness; this practice is about communication."
        ),
        "opening": "Hello, thank you for coming in today. Let's begin. {first_question}",
    },
    "workplace": {
        "label": "Workplace communication",
        "icon": ":material/groups:",
        "scenarios": ["Introducing yourself to colleagues", "Explaining a problem", "Asking for help",
                      "Participating in a meeting", "Giving a project update",
                      "Explaining a technical concept simply", "Handling a disagreement politely",
                      "Speaking to a manager", "Communicating with a customer"],
        "instruction": (
            "Role-play a realistic workplace situation: {scenario}. You play the colleague, "
            "manager or customer as appropriate. Keep it realistic and ask one thing at a time."
        ),
        "opening": "Let's practise: {scenario_lower}. I'll play the other person. You can start whenever you're ready.",
    },
    "presentation": {
        "label": "Presentation practice",
        "icon": ":material/co_present:",
        "scenarios": ["Introduce your project", "Explain a topic you know well",
                      "Present your college", "Pitch an idea"],
        "instruction": (
            "The learner is practising a short presentation: {scenario}. Act as a polite "
            "audience member. After each part, reply with at most two sentences: a short "
            "acknowledgement and, if useful, one audience question."
        ),
        "opening": "I'm ready to listen. Please start your presentation: {scenario_lower}. "
                   "When you finish, press 'End session & get feedback'.",
    },
    "roleplay": {
        "label": "Role-play",
        "icon": ":material/theater_comedy:",
        "scenarios": ["Interviewer and candidate", "Customer and support agent",
                      "Manager and employee", "Two colleagues discussing a project",
                      "Two people meeting for the first time"],
        "instruction": (
            "Role-play scenario: {scenario}. Choose the role opposite to the learner, stay in "
            "character until the learner ends the session or asks for feedback, and keep "
            "each reply short and natural."
        ),
        "opening": "Role-play: {scenario_lower}. I'm in character now. Go ahead and start.",
    },
    "free": {
        "label": "Free conversation",
        "icon": ":material/forum:",
        "scenarios": ["Anything you like"],
        "instruction": "Have an open, friendly conversation about whatever the learner wants.",
        "opening": "Hi! What would you like to talk about today?",
    },
}

FIRST_INTERVIEW_QUESTIONS = {
    "Self-introduction": "Could you please introduce yourself?",
    "Tell me about yourself": "Tell me about yourself.",
    "Strengths and weaknesses": "What would you say are your main strengths and one weakness?",
    "Project explanation": "Can you tell me about a project you worked on recently?",
    "Career goals": "Where do you see your career in the next few years?",
    "HR questions": "Why are you interested in this role?",
    "Behavioural questions (STAR)": "Tell me about a time you faced a difficult problem. What did you do?",
    "Technical interview communication": "Can you explain a technical concept you know well, as if to a non-technical person?",
    "Questions to ask the interviewer": "We're nearly done. Do you have any questions for me?",
}

PROFICIENCY_GUIDE = {
    "Beginner": "Use very simple words and short sentences (A1-A2 level).",
    "Elementary": "Use simple everyday English (A2 level).",
    "Intermediate": "Use clear, natural English (B1-B2 level).",
    "Advanced": "Use natural, fluent English (C1 level).",
}


def build_system_prompt(mode: str, scenario: str, proficiency: str, variety: str) -> str:
    """Build the system prompt that sets the AI's personality and task."""
    mode_info = MODES.get(mode, MODES["free"])
    level = PROFICIENCY_GUIDE.get(proficiency, PROFICIENCY_GUIDE["Intermediate"])
    return (
        "You are LinguaAI, a friendly, patient and practical English speaking partner.\n"
        f"{mode_info['instruction'].format(scenario=scenario)}\n"
        f"Language level: {level}\n"
        f"Use {variety} English spelling and expressions.\n"
        "Rules:\n"
        "- Your reply will be spoken aloud, so keep it to 1-3 short sentences.\n"
        "- No lists, no emojis, no markdown, no stage directions.\n"
        "- Do NOT correct the learner's grammar in your reply; feedback is given separately.\n"
        "- Be encouraging but honest. Never mock the learner.\n"
        "- The learner's words come from speech recognition and may contain recognition "
        "mistakes; if something is unclear, politely ask them to repeat."
    )


def opening_line(mode: str, scenario: str) -> str:
    mode_info = MODES.get(mode, MODES["free"])
    return mode_info["opening"].format(
        scenario=scenario,
        scenario_lower=scenario[:1].lower() + scenario[1:],
        first_question=FIRST_INTERVIEW_QUESTIONS.get(scenario, "Could you please introduce yourself?"),
    )


# ---------------------------------------------------------------------------
# Grammar feedback (structured JSON)
# ---------------------------------------------------------------------------
GRAMMAR_CATEGORIES = {
    "grammar": "Incorrect grammar",
    "word_choice": "Word choice",
    "awkward": "Awkward wording",
    "unnatural": "Unnatural phrasing",
    "inappropriate": "Not suitable for this context",
    "informal_ok": "Informal but acceptable",
}

GRAMMAR_SYSTEM_PROMPT = """You are an expert, kind English teacher. You check ONE sentence or short answer spoken by a learner.
The text came from speech recognition, so ignore missing punctuation and capital letters.
Do not correct informal English that is acceptable in conversation; label it "informal_ok" instead.
Remember there are often several correct ways to say something.
Use {variety} English. Explain simply for a {proficiency} learner. Avoid technical grammar terms.

Answer ONLY with a JSON object in exactly this shape:
{{
  "has_issues": true or false,
  "corrected": "the corrected sentence (same as original if nothing is wrong)",
  "issues": [
    {{"category": "grammar | word_choice | awkward | unnatural | inappropriate | informal_ok",
      "original": "the wrong part",
      "suggestion": "the better part",
      "explanation": "one short simple sentence"}}
  ],
  "alternatives": ["another natural way to say it", "a second way"],
  "practice": "one short practice question that makes the learner use the corrected pattern",
  "repeat_after_me": "one short natural sentence for the learner to repeat aloud"
}}
If there are no problems, use "has_issues": false and an empty "issues" list."""

GRAMMAR_USER_TEMPLATE = 'Context (what the learner was answering): "{context}"\nLearner said: "{text}"'


# ---------------------------------------------------------------------------
# Session feedback (structured JSON)
# ---------------------------------------------------------------------------
SESSION_FEEDBACK_SYSTEM_PROMPT = """You are an experienced English communication coach reviewing a practice session.
Session type: {mode_label} ({scenario}). Learner level: {proficiency}.
The learner's words came from speech recognition, which can make mistakes; do not blame the learner for obvious recognition errors.
You are evaluating COMMUNICATION (clarity, grammar, relevance, structure), not technical correctness.
Do not invent numbers or scores. Measured speaking statistics are provided; you may refer to them.

Answer ONLY with a JSON object in exactly this shape:
{{
  "summary": "2-3 sentence overall summary",
  "strengths": ["specific strength", "..."],
  "improvements": ["specific, actionable improvement", "..."],
  "clarity": "one or two sentences about clarity",
  "grammar": "one or two sentences about grammar patterns seen",
  "relevance": "one or two sentences about whether answers addressed the questions",
  "structure": "one or two sentences about how answers were organised",
  "vocabulary": "one or two sentences about vocabulary range",
  "next_steps": ["practical next practice step", "..."]
}}"""

SESSION_FEEDBACK_USER_TEMPLATE = """Conversation transcript:
{transcript}

Measured speaking statistics (from the recordings):
{metrics}"""


# ---------------------------------------------------------------------------
# Vocabulary lookup (structured JSON)
# ---------------------------------------------------------------------------
VOCAB_SYSTEM_PROMPT = """You are a helpful English dictionary for learners. Use {variety} English.
Explain the word or phrase simply for a {proficiency} learner.
Answer ONLY with a JSON object in exactly this shape:
{{
  "word": "the word",
  "definition": "simple definition",
  "example": "natural example sentence",
  "synonyms": ["synonym", "..."],
  "usage": "how and when it is commonly used",
  "register": "formal | neutral | informal",
  "collocations": ["common word combination", "..."],
  "practice_question": "a question that makes the learner use the word"
}}"""
