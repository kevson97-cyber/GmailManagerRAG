"""
run_mobile.py — Start Gmail RAG Assistant with a public ngrok tunnel.

Usage:  python run_mobile.py
        (or double-click run_mobile.bat)

What it does:
  1. Starts Streamlit on port 8501 (headless)
  2. Opens an ngrok HTTPS tunnel to that port
  3. Prints the public URL — open it on any phone / device anywhere

Requirements:
  - pyngrok installed  (pip install pyngrok)
  - NGROK_AUTHTOKEN set in .env  (free account at https://ngrok.com)
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# ── 1. Load .env ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(env_path)
except ImportError:
    print("[WARN] python-dotenv not installed — reading .env manually")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# ── 2. Pre-flight checks ──────────────────────────────────────────────────────
print("=" * 62)
print("  Gmail RAG Assistant — Mobile / Remote Access")
print("=" * 62)
print()

if not env_path.exists():
    print("[ERROR] .env file not found.")
    print("        Copy .env.example to .env and set OLLAMA_HOST / OLLAMA_MODEL.")
    input("\nPress Enter to exit...")
    sys.exit(1)

creds_path = BASE_DIR / "credentials" / "credentials.json"
if not creds_path.exists():
    print("[ERROR] credentials/credentials.json not found.")
    input("\nPress Enter to exit...")
    sys.exit(1)

# ── 3. Ensure pyngrok is installed ────────────────────────────────────────────
try:
    from pyngrok import ngrok, conf
except ImportError:
    print("[INFO] pyngrok not found — installing now...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyngrok>=7.0.0"])
    from pyngrok import ngrok, conf

# ── 4. ngrok auth token ───────────────────────────────────────────────────────
ngrok_token = os.getenv("NGROK_AUTHTOKEN", "").strip()

if not ngrok_token:
    print("To reach your app from anywhere you need a FREE ngrok account.")
    print()
    print("  1. Sign up (free):  https://ngrok.com/signup")
    print("  2. Copy your token: https://dashboard.ngrok.com/authtokens")
    print()
    token = input("Paste your ngrok auth token here: ").strip()
    if not token:
        print("\n[ERROR] No token entered. Cannot create public tunnel.")
        input("Press Enter to exit...")
        sys.exit(1)

    ngrok_token = token

    # Persist token into .env so user doesn't have to re-enter it next time
    with open(env_path, "a") as f:
        f.write(f"\nNGROK_AUTHTOKEN={token}\n")
    print("[OK] Token saved to .env — you won't be asked again.\n")

conf.get_default().auth_token = ngrok_token

# ── 5. Start Streamlit in background ─────────────────────────────────────────
print("[1/3] Starting Streamlit on port 8501...")

streamlit_proc = subprocess.Popen(
    [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", "8501",
        "--server.headless", "true",
        "--server.address", "0.0.0.0",
        "--browser.gatherUsageStats", "false",
    ],
    cwd=BASE_DIR,
)

# Give Streamlit a moment to start
time.sleep(4)

if streamlit_proc.poll() is not None:
    print("[ERROR] Streamlit failed to start. Check for errors above.")
    input("Press Enter to exit...")
    sys.exit(1)

# ── 6. Open ngrok tunnel ──────────────────────────────────────────────────────
print("[2/3] Creating ngrok tunnel...")

try:
    tunnel = ngrok.connect(8501, "http")
    public_url = tunnel.public_url
    # ngrok gives http:// — upgrade to https://
    if public_url.startswith("http://"):
        public_url = "https://" + public_url[7:]
except Exception as e:
    print(f"\n[ERROR] Could not create ngrok tunnel: {e}")
    print("\nCommon fixes:")
    print("  - Check your NGROK_AUTHTOKEN in .env is correct")
    print("  - Make sure you're connected to the internet")
    print("  - Only one ngrok tunnel is allowed on the free plan —")
    print("    close any other ngrok sessions first.")
    streamlit_proc.terminate()
    input("\nPress Enter to exit...")
    sys.exit(1)

# ── 7. Print URL ──────────────────────────────────────────────────────────────
print("[3/3] Tunnel open!")
print()
print("=" * 62)
print()
print("  Open this URL on your phone (or any device):")
print()
print(f"      {public_url}")
print()
print("  Local access (same computer):")
print("      http://localhost:8501")
print()
print("  NOTE: First-time Gmail connection must be done on this")
print("        computer — a browser will open here automatically.")
print()
print("  Press Ctrl+C to stop the server.")
print()
print("=" * 62)

# ── 8. Keep alive until Ctrl+C ───────────────────────────────────────────────
try:
    streamlit_proc.wait()
except KeyboardInterrupt:
    pass
finally:
    print("\nShutting down...")
    try:
        ngrok.kill()
    except Exception:
        pass
    streamlit_proc.terminate()
    print("Done.")
