"""
run_mobile_bg.pyw — Windowless launcher for GmailRAG mobile access.
Starts Streamlit + ngrok silently, writes the public URL to mobile_url.txt.
"""
import os, sys, subprocess, time
from pathlib import Path

BASE = Path(__file__).resolve().parent
URL_FILE = BASE / "mobile_url.txt"

# ── Load .env ─────────────────────────────────────────────────
env_path = BASE / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

URL_FILE.write_text("STARTING...\n", encoding="utf-8")

# ── Start Streamlit ───────────────────────────────────────────
streamlit_proc = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", str(BASE / "app.py"),
     "--server.port", "8501",
     "--server.headless", "true",
     "--server.address", "0.0.0.0",
     "--browser.gatherUsageStats", "false"],
    cwd=BASE,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(5)

# ── Open ngrok tunnel ─────────────────────────────────────────
try:
    from pyngrok import ngrok, conf
    token = os.environ.get("NGROK_AUTHTOKEN", "").strip()
    if token:
        conf.get_default().auth_token = token
    tunnel = ngrok.connect(8501, "http")
    public_url = tunnel.public_url
    if public_url.startswith("http://"):
        public_url = "https://" + public_url[7:]
    URL_FILE.write_text(f"READY\n{public_url}\n", encoding="utf-8")
except Exception as e:
    URL_FILE.write_text(f"ERROR: {e}\n", encoding="utf-8")
    streamlit_proc.terminate()
    sys.exit(1)

# ── Keep alive ────────────────────────────────────────────────
try:
    streamlit_proc.wait()
except Exception:
    pass
finally:
    try:
        ngrok.kill()
    except Exception:
        pass
    streamlit_proc.terminate()
