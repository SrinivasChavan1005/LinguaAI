# Privacy

LinguaAI is designed so that **nothing you say or type leaves your computer** during normal use.

## What is stored, and where

| What | Where | Stored? |
|---|---|---|
| Microphone audio | Browser memory → Python memory | **Never saved to disk.** It is discarded after transcription. In the Pronunciation Lab, your last attempt stays in memory until you leave the page, so you can replay it. |
| Transcripts and AI replies | `data\linguaai.db` | Yes, if **Settings → Conversation → Save history** is on (the default). Turn it off and nothing from new sessions is saved. |
| Grammar/session feedback and your ratings | `data\linguaai.db` | Yes (with history on) |
| Speaking metrics (WPM, fillers, pauses) | `data\linguaai.db` | Yes (with history on) |
| Vocabulary list and notes | `data\linguaai.db` | Yes |
| Learning profile | `data\linguaai.db` (`preferences` table) | Yes |
| Technical settings | `data\settings.json` | Yes |
| Logs | `logs\linguaai.log` | Timings, errors and **word counts only**. Your sentences are not logged. |

There are no passwords or accounts, because none are needed for a single-user local app.

## Which models run locally

| Job | Model | Runs in |
|---|---|---|
| Speech recognition | Faster-Whisper (`base.en` by default) | the LinguaAI Python process |
| Speech detection | Silero VAD (bundled in faster-whisper) | the LinguaAI Python process |
| Conversation, grammar, vocabulary, session feedback | Ollama model (`llama3.2:3b` by default) | the Ollama program on `127.0.0.1:11434` |
| Text-to-speech | Piper voice, or the built-in Windows voice | the LinguaAI process / Windows |

## What leaves the computer

- **During normal use: nothing.**
  - The app is only reachable at `127.0.0.1`.
  - Streamlit usage statistics are switched off.
  - Model libraries are forced into offline mode.
  - The Ollama address must be local.
- **During setup only:** packages are downloaded from PyPI. Models come from Hugging Face (Whisper, Piper voices) and the Ollama library. These downloads send ordinary download requests and no personal data.
- **Your own choices:** if the folder is inside OneDrive, OneDrive may upload `data\linguaai.db`. Keep the folder outside OneDrive to avoid this.

## How to delete your data

| What to delete | How |
|---|---|
| One session | **Conversation History** → choose session → **Delete this session** |
| All history | **Progress** → **Delete all history** (type DELETE). Optionally also deletes vocabulary. |
| One word | **Vocabulary → My words** → **Delete** |
| Everything | Close LinguaAI, then delete `data\linguaai.db` (and `data\linguaai.db-wal`, `-shm` if present), `data\settings.json` and `logs\*.log`. A fresh database is created next time. |
| Ollama models | `ollama rm llama3.2:3b` |

## Exporting your data

- **Progress → Export answers (CSV)** or **Export everything (JSON)**
- **Conversation History → Export this session (JSON)**
