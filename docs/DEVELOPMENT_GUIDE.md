# Development guide

## Project layout

```
app.py                     entry point: logging, database, navigation, sidebar status
config/settings.py         AppSettings dataclass (data/settings.json), validation, paths, model choices
config/prompts.py          every prompt sent to the language model, conversation modes and scenarios
core/llm_client.py         Ollama HTTP client (localhost only) with clear error types
core/conversation_engine.py  dialogue state, context trimming, saving turns
core/speech_recognition.py   Faster-Whisper wrapper (lazy load, CUDA→CPU notice, VAD)
core/speech_synthesis.py     Piper + Windows voice
core/grammar_analyzer.py     JSON grammar feedback + robust parsing
core/fluency_analyzer.py     WPM, fillers, pauses, repetitions (pure functions)
core/pronunciation_analyzer.py  reference vs. recognised word alignment (difflib)
core/feedback_engine.py      when to give feedback, session statistics, session feedback
core/learning_engine.py      daily plan + recommendations from real history
core/vocabulary_helper.py    word lookups (JSON)
core/performance_monitor.py  timings and memory
audio/audio_utils.py       WAV decode/encode, resampling, quality indicators
database/database.py       connection, schema, migrations
database/repository.py     all SQL queries (parameterised)
ui/                        Streamlit helpers: cached models, components, conversation view, profile form
pages/                     one file per page
scripts/                   setup, diagnostics, launcher helpers, benchmark
tests/                     pytest suite (no models, microphone or Ollama needed)
```

There is no `audio/recorder.py` or `audio/playback.py`. Recording and playback happen in the browser (see ARCHITECTURE.md for why).

## Everyday commands (PowerShell)

```powershell
.\venv\Scripts\Activate.ps1          # activate (if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)
python -m pytest -q                  # run tests
python -m pytest tests\test_grammar.py -v
python -m streamlit run app.py --server.address 127.0.0.1 --server.fileWatcherType auto   # auto-reload while coding
python scripts\benchmark.py
```

## Rules this codebase follows

- `core/` and `audio/` never import Streamlit, so they can be tested without a browser.
- Model output is untrusted. It is parsed with `json` and validated by `utils/validators.py`. It is never `eval`/`exec`'d and never executed.
- Every user-facing error is a specific exception (`LLMError`, `SpeechRecognitionError`, `SpeechSynthesisError`, `AudioError`, `DatabaseError`) whose message tells the user how to recover.
- Nothing downloads at runtime. Models come from `models/` and Ollama only.
- Logs never contain full user sentences. Use `utils.logging_config.redact()`.

## Common changes

**Add a scenario:** add it to the `scenarios` list of a mode in `config/prompts.py`.

**Add a conversation mode:** add an entry to `MODES` in `config/prompts.py` (label, scenarios, instruction, opening). Then add its key to the list in `pages/voice_practice.py`.

**Change the database:** append a new SQL string to `MIGRATIONS` in `database/database.py`, for example:
```python
MIGRATIONS.append("ALTER TABLE vocabulary ADD COLUMN topic TEXT NOT NULL DEFAULT ''")
```
Never edit an existing migration. Add a test in `tests/test_database.py`.

**Add a setting:** add a field with a safe default to `AppSettings`, a rule in `validate()`, a control in `pages/settings.py`, and a test in `tests/test_settings.py`.

**Add pronunciation sentences:** edit `data/exercises/pronunciation.json`. Use the same structure, and a new key creates a new practice set.

## Testing strategy

- Unit tests mock all hardware and services. `FakeLLM` in `tests/conftest.py` stands in for Ollama, and the `FakeSession` class in `test_components.py` stands in for HTTP.
- Real-model checks are **separate**: `scripts/benchmark.py` and the **Settings → Diagnostics** buttons exercise the actual Whisper, Piper and Ollama installs.
- Never delete a failing test to make the suite pass. Fix the code or the test's wrong assumption.

## Ideas for later

| Idea | Notes |
|---|---|
| Phoneme-level pronunciation scoring | e.g. a wav2vec2 phoneme model. Needs PyTorch (~1–2 GB disk, ~1 GB+ RAM), so it is not included for 8 GB laptops. Evaluate licenses first. |
| Streaming replies | Stream Ollama tokens and speak sentence-by-sentence to reduce waiting time. |
| Spaced repetition for vocabulary | e.g. SM-2 scheduling using `review_count`/`correct_count`. |
| Optional saving of recordings | Must be opt-in with explicit consent, and must have a delete button. |
