# Models folder

LinguaAI reads models **only** from this folder (and from Ollama). It never
downloads anything while the app is running.

| Folder / file | What it is | Size | License | Official source |
|---|---|---|---|---|
| `whisper/base.en/` (default) | Faster-Whisper speech recognition (CTranslate2 conversion of OpenAI Whisper) | ~145 MB | MIT | https://huggingface.co/Systran/faster-whisper-base.en |
| `whisper/tiny.en/` (optional) | Faster, less accurate | ~75 MB | MIT | https://huggingface.co/Systran/faster-whisper-tiny.en |
| `whisper/small.en/` (optional) | More accurate, slower | ~485 MB | MIT | https://huggingface.co/Systran/faster-whisper-small.en |
| `piper/en_US-lessac-medium.onnx` + `.onnx.json` (default) | Piper neural voice | ~63 MB | Voice-specific: read the voice's MODEL_CARD | https://huggingface.co/rhasspy/piper-voices |
| Ollama model `llama3.2:3b` (stored by Ollama, not here) | Language model | ~2.0 GB | Llama 3.2 Community License | https://ollama.com/library/llama3.2 |
| Ollama model `qwen2.5:1.5b` (lighter alternative) | Language model | ~1.0 GB | Apache 2.0 | https://ollama.com/library/qwen2.5 |

Download them with:

```powershell
venv\Scripts\python scripts\download_models.py
```

**Voice licenses:** Piper voices are trained on different datasets with
different terms. Before using a voice beyond personal practice, open its
`MODEL_CARD` on the Hugging Face page above and check the license yourself.

The Silero voice-activity-detection model used for measuring speaking time is
bundled inside the `faster-whisper` package (MIT license) - no download needed.
