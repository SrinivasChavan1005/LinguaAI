"""Wait until the local LinguaAI server answers, then open it in the default browser."""

import sys
import time
import urllib.request
import webbrowser

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8501
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for _ in range(60):
    try:
        with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=2):
            break
    except OSError:
        time.sleep(1)
webbrowser.open(f"http://localhost:{port}")
