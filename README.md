# LinguaAI — Offline Communication Coach

LinguaAI is a private English speaking coach that runs on your own Windows laptop:

- **You speak** into the microphone. **Faster-Whisper** turns your speech into text on your computer.
- **A local language model** running in **Ollama** replies as a friendly conversation partner, interviewer or role-play character.
- **Piper**, or the built-in Windows voice, reads the reply aloud.
- You get **grammar feedback**, **fluency measurements**, **pronunciation practice**, a **vocabulary builder** and a **progress dashboard**.
- Your history is saved in a local **SQLite** database.

After setup, everything works **without internet**. No API keys, no cloud services, and no audio is saved.

---

## 1. What you need

| Item | Notes |
|---|---|
| Windows 10/11, 64-bit | Built for laptops with about 8 GB RAM |
| **Python 3.11, 3.12 or 3.13 (64-bit)** | 3.12 is recommended. Get it from https://www.python.org/downloads/windows/ and tick **"Add python.exe to PATH"** during installation. |
| **Ollama for Windows** | https://ollama.com/download. It runs the language model locally. |
| About 4 GB free disk space | Packages (~0.6 GB) + models (~2.3 GB) |
| Internet **during setup only** | Needed to download packages and models |
| A microphone and a browser | Chrome or Edge recommended |

FFmpeg and Git are **not** required.

## 2. Put the folder on your Desktop

1. Extract the zip so that you have `C:\Users\<you>\Desktop\LinguaAI\app.py`.
   - If your Desktop is synced by **OneDrive**, the real path is `C:\Users\<you>\OneDrive\Desktop\LinguaAI`.
     OneDrive would upload your private practice data to the cloud and can lock files while syncing.
     In that case, extract to `C:\LinguaAI` instead. The setup script warns you about this.
   - To see where your Desktop really is, run this in PowerShell:
     ```powershell
     [Environment]::GetFolderPath("Desktop")
     ```

## 3. Install (once)

1. Install **Ollama** and start it. It appears as a llama icon in the system tray.
2. Double-click **`setup_linguaai.bat`**. It will:
   1. Find a supported Python.
   2. Create a virtual environment in `LinguaAI\venv`.
   3. Install the pinned packages from `requirements.txt`.
   4. **Ask before each download**:
      - speech model `base.en` (~145 MB)
      - voice `en_US-lessac-medium` (~63 MB)
      - language model `llama3.2:3b` (~2.0 GB, via Ollama)
   5. Create the database.
   6. Run a diagnostic check.

You can also do the same steps by hand in PowerShell:

```powershell
cd "$([Environment]::GetFolderPath('Desktop'))\LinguaAI"
py -3.12 -m venv venv
.\venv\Scripts\python -m pip install -r requirements.txt
.\venv\Scripts\python scripts\download_models.py
.\venv\Scripts\python scripts\init_db.py
```

## 4. Run

Double-click **`run_linguaai.bat`**. It:
- checks Python, the packages and Ollama, and tries to start Ollama if it isn't running;
- picks a free port, or opens the already-running copy instead of starting a second one;
- starts the app on `http://localhost:8501`. It is reachable **only from this computer**.

Your browser opens automatically. Keep the black window open while you practise, and close it to stop LinguaAI.

To start it from PowerShell instead:

```powershell
.\venv\Scripts\python -m streamlit run app.py --server.address 127.0.0.1
```

The first time you press the microphone, the browser asks for microphone permission. Choose **Allow**.

## 5. Check that everything works

| Command | What it does |
|---|---|
| `check_system.bat` | Read-only report: Python, RAM, disk, GPU, packages, Ollama, models, database, port |
| `.\venv\Scripts\python scripts\benchmark.py` | Speaks a test sentence, transcribes it, asks the AI one question, and **measures** each step on your laptop. Results are added to `logs\benchmark.log`. |
| `.\venv\Scripts\python -m pytest` | Runs the automated tests. No models or microphone needed. |
| In the app: **Settings → Diagnostics** | System check, memory use, average timings, and test buttons for each component |

**Test offline mode:** after setup, turn off Wi-Fi, run `run_linguaai.bat`, and have a short conversation.

## 6. Using LinguaAI

| Page | What you can do |
|---|---|
| **Dashboard** | First-launch profile (level, goal, daily minutes, British/American English, feedback timing), today's plan, recommendations based on your real history |
| **Voice Practice** | Daily conversation, workplace, presentation, role-play and free conversation. Speak or type. You get grammar feedback, speaking metrics, "Hear it" and "Practise" buttons for the repeat-after-me sentence, and can save words. |
| **Interview Practice** | The AI acts as an interviewer. At the end you get feedback on clarity, grammar, relevance and structure, plus your measured statistics. |
| **Pronunciation Lab** | Hear a sentence, record yourself, and see which words were recognised, missed or heard differently. This is approximate: it is not a sound-by-sound score. |
| **Vocabulary** | Look up words with the local AI, save them, add notes, mark them as mastered, and revise with a quiz |
| **Conversation History** | Re-read past sessions with their feedback. Export a session as JSON or delete it. |
| **Progress** | Charts built only from recorded data. Export as CSV/JSON, or delete all history. |
| **Settings** | Learning profile, models, voice, speaking speed, recording limit, history on/off, diagnostics |

## 7. Changing models

In **Settings → Models**, you can choose:
- **Whisper**: `tiny.en` / `base.en` / `small.en`
- **Ollama model**: any model you have installed
- **Voice**: Piper voice or the Windows voice

Changing a setting never downloads anything. To add a model:

```powershell
.\venv\Scripts\python scripts\download_models.py --whisper small.en --voice en_GB-alba-medium
ollama pull qwen2.5:1.5b
```

**If your laptop is slow or low on memory:** use `tiny.en` with `qwen2.5:1.5b` (about 1 GB). Grammar feedback from smaller models is noticeably less reliable. That's the trade-off.

## 8. More documentation

- `docs/ARCHITECTURE.md` explains how audio travels through the app, how the AI gets context, and how the database works.
- `docs/TROUBLESHOOTING.md` lists common errors and their fixes.
- `docs/PRIVACY.md` covers what is stored, where, and how to delete it.
- `docs/DEVELOPMENT_GUIDE.md` covers how to change and extend the code, and run tests.
- `docs/STATUS.md` lists what is done and tested, what isn't, and the next priorities.
- `models/README.md` lists models, sizes, licenses and official sources.
