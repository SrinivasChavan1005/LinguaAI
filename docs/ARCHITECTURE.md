# LinguaAI architecture (beginner-friendly)

## The big picture

```
 Browser (localhost only)                     Python process (Streamlit server)                Ollama (separate program)
 ───────────────────────                      ──────────────────────────────────                ─────────────────────────
 [mic button] ──WAV 16 kHz──▶ audio/audio_utils.py  decode + quality check
                                     │
                                     ▼
                              core/speech_recognition.py  Faster-Whisper (+ Silero VAD)
                                     │ text + word timings
                                     ├──▶ core/fluency_analyzer.py  (WPM, fillers, pauses)
                                     ▼
                              core/conversation_engine.py ──HTTP 127.0.0.1:11434──▶  llama3.2:3b
                                     │ reply text  ◀──────────────────────────────────┘
                                     ▼
                              core/speech_synthesis.py  Piper / Windows voice
 [audio player] ◀──WAV───────────────┘
                              core/grammar_analyzer.py  (JSON feedback, also via Ollama)
                              database/repository.py ──▶ data/linguaai.db (SQLite)
```

There are three layers:

| Layer | Folder | Knows about Streamlit? |
|---|---|---|
| Interface | `app.py`, `pages/`, `ui/` | yes |
| Logic | `core/`, `audio/` | no, so it can be tested on its own |
| Storage & config | `database/`, `config/`, `utils/` | no |

## How audio travels through the system

1. **Recording.** `st.audio_input` asks your browser to record. The browser shows a recording timer, and Windows shows its microphone indicator. Nothing records until you press the button.
2. **Upload to localhost.** When you press stop, the browser sends a WAV file (16 kHz) to the Streamlit server on `127.0.0.1`. The audio stays on your computer.
3. **Decode.** `audio_utils.decode_wav` turns the bytes into a NumPy array of floats between -1 and 1. It converts stereo to mono and resamples if needed.
4. **Quality check.** `analyze_quality` measures loudness, clipping and the share of voiced frames. Silent, empty or too-short recordings are rejected *before* the slow speech model runs, with a message explaining what to do.
5. **Voice activity detection.** The small Silero VAD model bundled with faster-whisper finds the speech parts.
6. **Speech recognition.** `SpeechRecognizer.transcribe` runs Whisper with `word_timestamps=True`. The model is loaded once and cached with `st.cache_resource`, so it is not reloaded for every sentence.
7. **Measurements.** `fluency_analyzer` turns the word timings into speaking time, words per minute, filler words, pauses and repetitions.
8. **The audio is dropped.** It is not written to disk.

**Why not record with `sounddevice` in Python?** Streamlit code runs on a server thread. Recording there would block the page, show no recording indicator in the browser, and be hard to cancel. Browser recording gives a visible indicator, a cancel (trash) button and normal microphone permissions. Playback also happens in the browser's audio player, which avoids "audio device busy" problems in Python.

## How the language model receives context

`ConversationEngine.build_llm_messages()` sends this to Ollama:

```
[ system: role + scenario + your level + British/American + rules ]   ← config/prompts.py
[ the last N messages (N = "context_turns", default 8) ]
```

- Older messages are **not sent**. They stay on screen and in the database. This keeps each request small, fast and light on RAM (`num_ctx` = 2048 tokens).
- The reply is limited to `max_reply_tokens`. The prompt asks for 1–3 short spoken sentences.
- Grammar checks are **separate requests**. Each one sends one answer plus the AI question before it, and Ollama is asked for JSON (`format: "json"`). The JSON is validated field by field (`parse_grammar_response`). If it's broken, the result is a friendly "feedback could not be read" message and the app does not crash.
- `keep_alive = 10m` keeps the model in RAM between turns, so it isn't reloaded each time.

## When feedback happens

`feedback_engine.turns_due_for_feedback()` applies your chosen timing: every answer, every 3 answers, end of session, or only when asked. The page plays the AI's reply first, then checks grammar while the reply is playing, so feedback doesn't slow down the conversation.

## How the database stores sessions and feedback

```
sessions (id, mode, scenario, started_at, ended_at)
   └── turns (session_id → sessions.id, role, text, input_type,
              recording_seconds, speaking_seconds, word_count, words_per_minute,
              filler_count, long_pauses, metrics_json)
   └── feedback (session_id, turn_id, kind = grammar | session | pronunciation,
                 payload_json, user_rating = helpful | wrong | dismissed)
vocabulary (word UNIQUE NOCASE, definition, example, synonyms_json, ..., notes, mastered,
            review_count, correct_count)
practice_attempts (kind, reference, response, result_json)
preferences (key, value_json)            ← your learning profile
```

- All queries use `?` placeholders, so text you type can never change the SQL.
- `ON DELETE CASCADE`: deleting a session also deletes its turns and feedback.
- **Migrations:** `PRAGMA user_version` stores the schema version. `database.initialize()` applies any missing migration inside a transaction at startup. To change the schema later, *append* a new SQL string to `MIGRATIONS`. Never edit an old one.
- Feedback marked **wrong** or **dismissed** is ignored in statistics and recommendations.

## Models and memory (8 GB laptop)

| Component | Where it runs | Approx. RAM |
|---|---|---|
| Whisper `base.en` int8 | Python process | ~300–400 MB |
| Piper medium voice | Python process | ~100 MB |
| Streamlit + Python | Python process | ~200 MB |
| `llama3.2:3b` (Q4) | Ollama process | ~3–3.5 GB with 2k context |

These are estimates. Run `scripts\benchmark.py` or open **Settings → Diagnostics** to measure on your laptop.

- Models load **lazily**, the first time they are needed.
- `max_entries=1` on the caches means switching models releases the old one.
- CUDA is used only if `ctranslate2` finds a GPU **and** the model loads. Otherwise the app uses the CPU and shows a notice. It never switches silently.

## Offline guarantees

- `app.py` sets `HF_HUB_OFFLINE=1`, and models load with `local_files_only=True`, so nothing is downloaded at runtime.
- The Ollama host must be `localhost`/`127.0.0.1`. Settings refuses anything else, and local requests ignore system proxies.
- Streamlit is bound to `127.0.0.1` and has usage statistics turned off (`.streamlit/config.toml`).
