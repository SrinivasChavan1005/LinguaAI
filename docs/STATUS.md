# Project status

Last updated: 26 October 2026, first build.

## Where this build was made

It was built and tested in a **Linux cloud workspace**, not on your Windows laptop. That workspace:
- could install Python packages;
- **could not download models**, because Hugging Face and the Ollama registry were blocked;
- had no microphone or speakers.

The results below say exactly what was and wasn't verified.

## Automated tests: passed

`python -m pytest`: **86 passed** (Python 3.13, Linux). The suite covers:
- grammar output parsing, including malformed, truncated, wrongly typed and non-JSON model output;
- empty transcripts, fluency calculations, feedback timing and session statistics;
- database creation, idempotent migrations, a corrupted database file, a newer schema, cascade deletes, SQL-injection text, conversation persistence, vocabulary and preferences;
- settings loading, invalid values, a corrupted settings file, a remote Ollama host being rejected, environment overrides;
- missing Whisper model, missing Piper voice, Windows voice used off Windows;
- invalid or empty audio, silence and clipping detection, stereo→mono and resampling;
- Ollama not running, model missing (404), timeout, success payload;
- pronunciation word alignment, vocabulary parsing, input validation.

The Silero VAD bundled with faster-whisper was run for real in one test, on silent audio.

## Manual browser tests: done in the cloud workspace

Done with a headless Chromium. **A stand-in Ollama server returning fixed replies** was used, because the real Ollama couldn't be installed there. These tests check the interface and data flow, **not** the AI's quality.
- Onboarding → dashboard → start a session → typed answers → reply shown once (no duplicates) → grammar feedback panel → "Helpful" rating → end session → session feedback.
- Every page loads without errors: Interview, Pronunciation, Vocabulary (look up → save → listed), History, Progress, Settings (system check, "Test AI model", "Test voice").
- Simulated microphone (fake audio device): the recording indicator shows, and the clear "speech model not found" and "voice not found" messages appear. There was no crash.
- Two bugs were found and fixed:
  - a damaged database file crashed instead of showing a message;
  - a duplicate-key crash on the session feedback screen.

## Not yet tested (needs your Windows laptop)

- [ ] `setup_linguaai.bat`, `run_linguaai.bat`, `check_system.bat` on real Windows. They were written carefully but never executed on Windows.
- [ ] Real Faster-Whisper transcription (`base.en`) on your CPU, and its speed
- [ ] Real Ollama `llama3.2:3b` replies, and the quality of the JSON grammar feedback
- [ ] Real Piper voice output, and the Windows built-in voice
- [ ] A real microphone recording through Chrome/Edge
- [ ] Memory use and end-to-end latency on 8 GB RAM. Run `scripts\benchmark.py` and Settings → Diagnostics.
- [ ] Offline operation with Wi-Fi turned off
- [ ] CUDA GPU path, if you have an NVIDIA GPU

## Implemented features

- Turn-based voice conversation: browser microphone → Whisper → Ollama → Piper/Windows voice, with typing as a fallback
- Modes: daily, workplace, presentation, role-play, free, and interview with end-of-session feedback
- Grammar feedback with categories, alternatives, a practice question, repeat-after-me ("Hear it" / "Practise"), and helpful/wrong/dismiss ratings
- Feedback timing: every answer, every 3 answers, end of session, or on request
- Fluency metrics: speaking time vs. recording time, WPM, fillers, long pauses, repetitions, sentence length, continuity
- Pronunciation Lab: reference vs. recognised words, low-confidence words, audio quality, spelling-based practice-set hints (clearly labelled as approximate)
- Vocabulary: AI lookup, save (also from a conversation), notes, mastered, revision quiz, delete
- Dashboard: onboarding profile, daily plan, recommendations from real data (marked preliminary when there's little data)
- Progress: charts from real data only, CSV/JSON export, delete all
- History: browse sessions with feedback, export, delete
- Settings: models, voice, speed, limits, history on/off, diagnostics, memory, timings, component tests
- Offline safeguards, a localhost-only server, privacy-safe logs

## Known limitations

- Pronunciation analysis is word-level, not phoneme-level.
- Filler counts are a minimum, because Whisper can drop "um"/"uh" even with the prompt that tries to keep them.
- Grammar feedback quality depends on the local model. Smaller models make more mistakes, which is why the ratings exist.
- No streaming: you hear the reply after it is fully generated.
- You can't record and hear the AI at the same time. It's turn-based by design.
- The recording limit is enforced after recording: extra audio is cut off, and a note tells you so.

## Next three priorities

1. **Run setup on your laptop and measure.** Use `scripts\benchmark.py` and pick the right model sizes based on the numbers.
2. **Tune the prompts with real `llama3.2:3b` output.** Check how reliable the grammar JSON is on 20–30 real sentences. If it's poor, try `qwen2.5:3b`, though check its license first.
3. **Reduce waiting time.** Stream the Ollama reply and speak it sentence by sentence.
