# Troubleshooting

First run **`check_system.bat`**. It is read-only and flags most problems with a fix.
Logs are in `logs\linguaai.log`.

All commands below are for **PowerShell**, run inside the LinguaAI folder:

```powershell
cd "$([Environment]::GetFolderPath('Desktop'))\LinguaAI"
```

## Python

| Problem | Fix |
|---|---|
| `Python 3.11, 3.12 or 3.13 (64-bit) was not found` | Install Python 3.12 64-bit from python.org and tick **Add python.exe to PATH**. Then close and reopen the terminal and run `py -0` to list installed versions. |
| Typing `python` opens the Microsoft Store | Settings → Apps → Advanced app settings → **App execution aliases** → turn off `python.exe`/`python3.exe`, or use `py -3.12`. |
| Wrong Python version in an old `venv` | Rename `venv` to `venv_old` and run `setup_linguaai.bat` again. |

## Installing packages

| Problem | Fix |
|---|---|
| `pip install` fails with "No matching distribution" | You are probably on Python 3.10, 3.14 or 32-bit Python. Install Python 3.12 64-bit (see above). |
| SSL / proxy / timeout errors | Check your internet connection. On a company network try `.\venv\Scripts\python -m pip install -r requirements.txt --proxy http://your-proxy:port`. |
| `Microsoft Visual C++ ... required` | Shouldn't happen with the pinned versions (all have ready-made Windows wheels). Install the "Microsoft Visual C++ Redistributable (x64)" from Microsoft and retry. |
| `onnxruntime` DLL load failed | Install the latest **Microsoft Visual C++ Redistributable (x64)** and restart. |

## Microphone

| Problem | Fix |
|---|---|
| Browser never asks for permission / "Permission denied" | Click the lock or settings icon left of `localhost:8501` → Microphone → **Allow**, then reload. |
| Windows blocks it | Settings → Privacy & security → **Microphone** → allow access, including "Let desktop apps access your microphone". |
| Wrong microphone | In Chrome/Edge: lock icon → Site settings → choose the microphone. Or set the default device in Windows Sound settings. |
| Device busy | Close Teams/Zoom/Discord calls that hold the microphone, then reload the page. |
| "No speech was detected" | The recording was silent. Check that the mic isn't muted (hardware key) and the input level in Windows Sound settings. |
| "The recording is very quiet" | Move closer or raise the input volume. |
| "I couldn't recognise any words" | Speak a little slower and closer. Background noise can also cause this. |

## Speech recognition (Whisper)

| Problem | Fix |
|---|---|
| `Speech recognition model 'base.en' was not found` | Run `.\venv\Scripts\python scripts\download_models.py` once with internet. |
| `Could not load the speech recognition model ... corrupted` | Delete `models\whisper\base.en` and run the download script again. |
| Very slow (> 10 s per sentence) | Choose `tiny.en` in Settings → Models, and keep precision at `int8`. Close other heavy programs. |
| `GPU (CUDA) could not be used` notice | Normal if NVIDIA CUDA 12 / cuDNN 9 libraries are missing. The CPU works fine. To silence it, set Device to `cpu`. |
| Not enough memory | Use `tiny.en`, close browser tabs, or use a smaller Ollama model. |

## Ollama / language model

| Problem | Fix |
|---|---|
| `Ollama is not running` | Start **Ollama** from the Start menu (llama icon in the tray), or run `ollama serve` in a separate terminal. |
| `Model 'llama3.2:3b' is not installed` | `ollama pull llama3.2:3b`. Check with `ollama list`. |
| Invalid model name | `ollama list` shows exact names. Choose one in Settings → Models. |
| `Not enough memory to load` | `ollama pull qwen2.5:1.5b` and select it in Settings. Close other programs. |
| `The language model took longer than 120s` | The first reply after starting includes loading the model (can take 30–60 s on a slow disk). If it happens every time, use a smaller model. |
| `ollama` is not recognised as a command | Reinstall Ollama, or use the full path `& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" list`. |

## Voice (text-to-speech)

| Problem | Fix |
|---|---|
| `Piper voice ... was not found` | Run the download script, or choose **Windows built-in** voice in Settings → Models. |
| `Could not load Piper voice` | Delete the voice's `.onnx` and `.onnx.json` in `models\piper` and download again. |
| Windows voice fails | Check PowerShell works: `powershell -Command "Add-Type -AssemblyName System.Speech"`. Make sure at least one voice is installed (Settings → Time & language → Speech). |
| Reply is not spoken automatically | The browser blocked autoplay. Click play once, or allow sound for `localhost` in site settings. Check **Play AI replies automatically** in Settings. |
| Stop the voice | Press **Stop voice** under the reply, or pause the audio player. |

## App / launcher

| Problem | Fix |
|---|---|
| "LinguaAI seems to be running already" | It opened the existing tab. To restart, close the other black LinguaAI window first. |
| Ports 8501–8510 all busy | Close other Streamlit apps, or restart the computer. Check with `netstat -ano | findstr :8501`. |
| Browser didn't open | Open `http://localhost:8501` manually (or the port shown in the window). |
| A page shows a red error box | Copy the message and check `logs\linguaai.log`. Reloading the page usually recovers. |
| `Database problem ... seems damaged` | Close LinguaAI and rename `data\linguaai.db` to `linguaai_broken.db`. A fresh database is created on next start. |
| `created by a newer LinguaAI` | You opened a newer database with older code. Update the code. |
| Changes to code don't appear | File watching is off (saves CPU). Close and restart `run_linguaai.bat`. |

## Getting diagnostic details

```powershell
.\venv\Scripts\python scripts\diagnose.py      # same as check_system.bat
.\venv\Scripts\python scripts\benchmark.py     # measures each component
Get-Content logs\linguaai.log -Tail 50         # last log lines
.\venv\Scripts\python -m pytest -q             # automated tests
```
