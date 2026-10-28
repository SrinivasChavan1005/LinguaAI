"""
Read-only system checks used by ``check_system.bat``, the setup script and the
Settings page. Nothing here modifies or deletes files.

This module only needs the Python standard library, so it also works before
the virtual environment is created.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import socket
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUPPORTED_PYTHON = ((3, 11), (3, 13))   # inclusive range with tested Windows wheels
REQUIRED_PACKAGES = ("streamlit", "faster_whisper", "piper", "numpy", "scipy", "pandas", "requests", "psutil")


@dataclass
class Check:
    name: str
    status: str        # "ok", "warn", "fail", "info"
    detail: str
    fix: str = ""


def check_python() -> Check:
    v = sys.version_info
    text = f"Python {v.major}.{v.minor}.{v.micro} ({platform.architecture()[0]})"
    lo, hi = SUPPORTED_PYTHON
    if (v.major, v.minor) < lo or (v.major, v.minor) > hi:
        return Check("Python", "fail", text,
                     "Install Python 3.12 (64-bit) from https://www.python.org/downloads/windows/ "
                     "and tick 'Add python.exe to PATH'.")
    if platform.architecture()[0] != "64bit":
        return Check("Python", "fail", text, "Install the 64-bit version of Python.")
    return Check("Python", "ok", text)


def check_os() -> Check:
    return Check("Operating system", "info", f"{platform.system()} {platform.release()} ({platform.machine()})")


def check_project_location() -> Check:
    path = str(PROJECT_ROOT)
    if "onedrive" in path.lower():
        return Check("Project folder", "warn", path,
                     "The folder is inside OneDrive. Syncing can lock files and upload your data. "
                     "Consider moving it to a local folder such as C:\\LinguaAI.")
    return Check("Project folder", "ok", path)


def check_disk(min_gb: float = 5.0) -> Check:
    usage = shutil.disk_usage(PROJECT_ROOT)
    free_gb = usage.free / 1e9
    status = "ok" if free_gb >= min_gb else "warn"
    return Check("Free disk space", status, f"{free_gb:.1f} GB free",
                 "" if status == "ok" else f"At least {min_gb:.0f} GB is recommended for models.")


def total_ram_gb() -> float | None:
    try:
        import psutil

        return psutil.virtual_memory().total / 1e9
    except ImportError:
        pass
    if platform.system() == "Windows":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat.ullTotalPhys / 1e9
    elif hasattr(os, "sysconf"):
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
        except (ValueError, OSError):
            return None
    return None


def check_ram() -> Check:
    ram = total_ram_gb()
    if ram is None:
        return Check("RAM", "info", "Could not detect")
    if ram < 7:
        return Check("RAM", "warn", f"{ram:.1f} GB",
                     "Less than 8 GB: use whisper 'tiny.en' and Ollama model 'qwen2.5:1.5b'.")
    return Check("RAM", "ok", f"{ram:.1f} GB")


def check_gpu() -> Check:
    if importlib.util.find_spec("ctranslate2") is None:
        return Check("GPU (CUDA)", "info", "Not checked (packages not installed yet)")
    try:
        import ctranslate2

        n = ctranslate2.get_cuda_device_count()
    except Exception as exc:  # driver problems raise various errors
        return Check("GPU (CUDA)", "info", f"Not available ({exc})")
    if n:
        return Check("GPU (CUDA)", "info", f"{n} CUDA device(s). Speech recognition will try the GPU "
                     "(needs NVIDIA cuBLAS/cuDNN); it falls back to CPU with a notice if that fails.")
    return Check("GPU (CUDA)", "info", "No CUDA GPU - CPU will be used (this is fine).")


def check_packages() -> Check:
    missing = [p for p in REQUIRED_PACKAGES if importlib.util.find_spec(p) is None]
    if missing:
        return Check("Python packages", "fail", "Missing: " + ", ".join(missing),
                     "Run setup_linguaai.bat to install them.")
    return Check("Python packages", "ok", "All required packages installed")


def check_ffmpeg() -> Check:
    path = shutil.which("ffmpeg")
    return Check("FFmpeg", "info", path or "Not installed",
                 "" if path else "Not required: LinguaAI reads WAV audio directly.")


def find_ollama() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(candidate) if candidate.is_file() else None


def ollama_models(host: str = "http://127.0.0.1:11434") -> list[str] | None:
    """Installed Ollama models, or None if Ollama is not reachable."""
    try:
        handler = urllib.request.ProxyHandler({})  # never use a proxy for localhost
        opener = urllib.request.build_opener(handler)
        with opener.open(f"{host}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", [])]
    except (OSError, ValueError):
        return None


def load_settings_dict() -> dict:
    path = PROJECT_ROOT / "data" / "settings.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def check_ollama() -> list[Check]:
    settings = load_settings_dict()
    model = settings.get("ollama_model", "llama3.2:3b")
    exe = find_ollama()
    checks = [Check("Ollama installed", "ok" if exe else "fail", exe or "Not found",
                    "" if exe else "Download Ollama for Windows from https://ollama.com/download")]
    models = ollama_models(settings.get("ollama_host", "http://127.0.0.1:11434"))
    if models is None:
        checks.append(Check("Ollama running", "warn", "Not reachable on 127.0.0.1:11434",
                            "Start the Ollama app from the Start menu (or run: ollama serve)."))
        return checks
    checks.append(Check("Ollama running", "ok", f"{len(models)} model(s) installed"))
    wanted = model if ":" in model else f"{model}:latest"
    checks.append(Check(f"Language model '{model}'", "ok" if wanted in models else "fail",
                        "Installed" if wanted in models else "Not installed",
                        "" if wanted in models else f"Run: ollama pull {model}"))
    return checks


def check_whisper_model() -> Check:
    name = load_settings_dict().get("whisper_model", "base.en")
    folder = PROJECT_ROOT / "models" / "whisper" / name
    ok = (folder / "model.bin").is_file() and (folder / "config.json").is_file()
    return Check(f"Speech model '{name}'", "ok" if ok else "fail", str(folder) if ok else "Not downloaded",
                 "" if ok else "Run: venv\\Scripts\\python scripts\\download_models.py")


def check_piper_voice() -> Check:
    settings = load_settings_dict()
    if settings.get("tts_engine", "piper") == "windows":
        return Check("Voice", "ok", "Using the built-in Windows voice")
    voice = settings.get("piper_voice", "en_US-lessac-medium")
    folder = PROJECT_ROOT / "models" / "piper"
    ok = (folder / f"{voice}.onnx").is_file() and (folder / f"{voice}.onnx.json").is_file()
    return Check(f"Piper voice '{voice}'", "ok" if ok else "fail", "Installed" if ok else "Not downloaded",
                 "" if ok else "Run: venv\\Scripts\\python scripts\\download_models.py "
                               "(or choose the Windows voice in Settings)")


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def check_port(port: int = 8501) -> Check:
    if port_in_use(port):
        return Check(f"Port {port}", "warn", "Already in use",
                     "LinguaAI may already be running - check your browser tabs. Otherwise "
                     "the launcher will use another port.")
    return Check(f"Port {port}", "ok", "Free")


def check_database() -> Check:
    path = PROJECT_ROOT / "data" / "linguaai.db"
    if not path.exists():
        return Check("Database", "info", "Not created yet (created on first launch)")
    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        ok = conn.execute("PRAGMA quick_check").fetchone()[0]
        conn.close()
    except sqlite3.Error as exc:
        return Check("Database", "fail", str(exc), "See docs\\TROUBLESHOOTING.md (database damaged).")
    return Check("Database", "ok" if ok == "ok" else "fail", f"Schema v{version}, integrity: {ok}")


def run_all_checks() -> list[Check]:
    checks = [check_os(), check_python(), check_project_location(), check_disk(), check_ram(),
              check_gpu(), check_packages(), check_ffmpeg()]
    checks += check_ollama()
    checks += [check_whisper_model(), check_piper_voice(), check_database(), check_port()]
    return checks
