"""
Pre-launch check used by run_linguaai.bat.

Writes the port to use into logs/launch_port.txt. Exit codes:
  0 = OK to start on that port
  2 = a Streamlit app (normally LinguaAI) is already running on that port: open it instead
  1 = a required piece is missing (message printed)
"""

from __future__ import annotations

import importlib.util
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.system_checks import (REQUIRED_PACKAGES, check_python, find_ollama, ollama_models,  # noqa: E402
                                 port_in_use)


def try_start_ollama() -> bool:
    """Start Ollama in the background if it is installed but not running."""
    import subprocess
    import time

    exe = find_ollama()
    if not exe:
        return False
    app = Path(exe).with_name("ollama app.exe")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        if app.is_file():
            subprocess.Popen([str(app)], creationflags=flags, close_fds=True)
        else:
            subprocess.Popen([exe, "serve"], creationflags=flags, close_fds=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    for _ in range(15):
        time.sleep(1)
        if ollama_models() is not None:
            return True
    return False


def is_streamlit(port: int) -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as resp:
            return resp.status == 200
    except OSError:
        return False


def main() -> int:
    py = check_python()
    if py.status == "fail":
        print(f"[FAIL] {py.detail}. {py.fix}")
        return 1
    missing = [p for p in REQUIRED_PACKAGES if importlib.util.find_spec(p) is None]
    if missing:
        print(f"[FAIL] Missing packages: {', '.join(missing)}. Run setup_linguaai.bat first.")
        return 1
    if ollama_models() is None:
        print("[INFO] Ollama is not running - trying to start it...")
        if try_start_ollama():
            print("[ OK ] Ollama started.")
        else:
            print("[WARN] Could not start Ollama. Start the Ollama app from the Start menu; LinguaAI "
                  "will show what is missing until it is running.")
    port_file = Path(__file__).resolve().parent.parent / "logs" / "launch_port.txt"
    port_file.parent.mkdir(exist_ok=True)
    for port in range(8501, 8511):
        if not port_in_use(port):
            port_file.write_text(str(port), encoding="ascii")
            return 0
        if is_streamlit(port):
            port_file.write_text(str(port), encoding="ascii")
            print(f"[INFO] LinguaAI seems to be running already on port {port}.")
            return 2
    print("[FAIL] Ports 8501-8510 are all busy.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
