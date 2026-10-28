"""
Download the models LinguaAI needs - run ONCE while connected to the internet.

    venv\\Scripts\\python scripts\\download_models.py            (asks before each download)
    venv\\Scripts\\python scripts\\download_models.py --yes      (no questions)

Sources (official only):
* Speech recognition: Systran/faster-whisper-* on Hugging Face (MIT license),
  downloaded with faster-whisper's own helper.
* Voices: rhasspy/piper-voices on Hugging Face, downloaded with Piper's own
  helper. Each voice has its own license - see its MODEL_CARD on Hugging Face.
* Language model: pulled by Ollama from the official Ollama library.

Nothing is downloaded without showing the size and asking first (unless --yes).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (MODELS_DIR, OLLAMA_MODEL_SUGGESTIONS, PIPER_VOICES_DIR,  # noqa: E402
                             WHISPER_MODEL_CHOICES, WHISPER_MODELS_DIR, AppSettings)
from utils.system_checks import find_ollama, ollama_models  # noqa: E402

APPROX_MB = {"tiny.en": 75, "base.en": 145, "small.en": 485, "piper_voice": 65,
             "llama3.2:3b": 2000, "qwen2.5:1.5b": 990, "llama3.2:1b": 1300}


def ask(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        print(f"{question} [auto-yes]")
        return True
    try:
        return input(f"{question} [y/N]: ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def free_mb() -> float:
    return shutil.disk_usage(MODELS_DIR).free / 1e6


def download_whisper(name: str, assume_yes: bool) -> bool:
    target = WHISPER_MODELS_DIR / name
    if (target / "model.bin").is_file():
        print(f"[ok] Speech model '{name}' already present.")
        return True
    size = APPROX_MB.get(name, 200)
    if free_mb() < size * 2:
        print(f"[!!] Not enough disk space for '{name}' (~{size} MB needed).")
        return False
    if not ask(f"Download speech recognition model '{name}' (~{size} MB, MIT license)?", assume_yes):
        return False
    from faster_whisper.utils import download_model

    print("     Downloading... (this can take a few minutes)")
    try:
        download_model(name, output_dir=str(target))
    except Exception as exc:  # network errors come from several libraries
        print(f"[!!] Download failed: {exc}")
        return False
    print(f"[ok] Saved to {target}")
    return True


def download_piper(voice: str, assume_yes: bool) -> bool:
    if (PIPER_VOICES_DIR / f"{voice}.onnx").is_file() and (PIPER_VOICES_DIR / f"{voice}.onnx.json").is_file():
        print(f"[ok] Voice '{voice}' already present.")
        return True
    print(f"     Voice licenses differ. Check: https://huggingface.co/rhasspy/piper-voices (MODEL_CARD of '{voice}')")
    if not ask(f"Download Piper voice '{voice}' (~{APPROX_MB['piper_voice']} MB)?", assume_yes):
        return False
    from piper.download_voices import download_voice

    PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    try:
        download_voice(voice, PIPER_VOICES_DIR)
    except Exception as exc:
        print(f"[!!] Download failed: {exc}")
        return False
    print(f"[ok] Saved to {PIPER_VOICES_DIR}")
    return True


def pull_ollama(model: str, assume_yes: bool) -> bool:
    exe = find_ollama()
    if not exe:
        print("[!!] Ollama is not installed. Install it from https://ollama.com/download then run this again.")
        return False
    installed = ollama_models()
    if installed is None:
        print("[!!] Ollama is installed but not running. Start the Ollama app, then run this again.")
        return False
    wanted = model if ":" in model else f"{model}:latest"
    if wanted in installed:
        print(f"[ok] Language model '{model}' already installed.")
        return True
    size = APPROX_MB.get(model, 2000)
    print(f"     {OLLAMA_MODEL_SUGGESTIONS.get(model, '')}")
    if not ask(f"Download language model '{model}' with Ollama (~{size} MB)?", assume_yes):
        return False
    result = subprocess.run([exe, "pull", model])
    return result.returncode == 0


def main() -> int:
    settings = AppSettings.load()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="download without asking")
    parser.add_argument("--whisper", default=settings.whisper_model, choices=list(WHISPER_MODEL_CHOICES))
    parser.add_argument("--voice", default=settings.piper_voice)
    parser.add_argument("--ollama-model", default=settings.ollama_model)
    parser.add_argument("--skip-ollama", action="store_true")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Free disk space: {free_mb() / 1000:.1f} GB\n")
    results = {
        "Speech recognition": download_whisper(args.whisper, args.yes),
        "Voice": download_piper(args.voice, args.yes),
    }
    if not args.skip_ollama:
        results["Language model"] = pull_ollama(args.ollama_model, args.yes)
    print("\nSummary:")
    for name, ok in results.items():
        print(f"  {'[ok]' if ok else '[--]'} {name}")
    if not all(results.values()):
        print("\nSome models are missing. LinguaAI will tell you what is missing when you start it.")
        return 1
    print("\nAll models are ready. LinguaAI can now run without internet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
