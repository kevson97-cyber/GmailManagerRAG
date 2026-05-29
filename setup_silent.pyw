"""
setup_silent.pyw — Windowless Python setup script.
Runs without a console window; writes all output to setup_log.txt.
Double-click to run from File Explorer.
"""
import subprocess, sys, os, shutil
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent
LOG  = BASE / "setup_log.txt"

def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)  # also to stdout (invisible in .pyw, but harmless)

log("=" * 60)
log(f"  GmailManagerRAG Setup  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log("=" * 60)

# ── 1. Find Ollama ────────────────────────────────────────────
log("\n[1/3] Checking Ollama...")
OLLAMA_EXE = None

# Try PATH first
if shutil.which("ollama"):
    OLLAMA_EXE = "ollama"
    log("[OK] ollama found in PATH")
else:
    # Try known installation paths
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "ollama.exe",
        Path("C:/Users") / os.environ.get("USERNAME", "") / "AppData/Local/Programs/Ollama/ollama.exe",
    ]
    for p in candidates:
        if p.exists():
            OLLAMA_EXE = str(p)
            log(f"[OK] Found ollama at: {p}")
            break

if OLLAMA_EXE is None:
    log("[!] ollama.exe not found. Setup will continue without model pull.")
    log("    Make sure Ollama is running (it was opened as an app already).")
else:
    # Check for llama3.2
    result = subprocess.run([OLLAMA_EXE, "list"], capture_output=True, text=True)
    log(f"    Installed models:\n{result.stdout.strip()}")
    if "llama3.2" not in result.stdout.lower():
        log("[  ] Pulling llama3.2 model (~2GB — this may take several minutes)...")
        result2 = subprocess.run([OLLAMA_EXE, "pull", "llama3.2"],
                                  capture_output=True, text=True)
        if result2.returncode == 0:
            log("[OK] llama3.2 model pulled successfully.")
        else:
            log(f"[!] Pull failed: {result2.stderr.strip()}")
    else:
        log("[OK] llama3.2 model already installed.")

# ── 2. Create .env ────────────────────────────────────────────
log("\n[2/3] Setting up .env file...")
env_file = BASE / ".env"
env_example = BASE / ".env.example"
if not env_file.exists():
    if env_example.exists():
        shutil.copy(env_example, env_file)
        log(f"[OK] Created .env from .env.example")
    else:
        log("[!] .env.example not found — skipping")
else:
    log("[OK] .env already exists.")

# ── 3. Install Python deps ────────────────────────────────────
log("\n[3/3] Installing Python dependencies...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", str(BASE / "requirements.txt")],
    capture_output=True, text=True
)
log(result.stdout[-3000:] if result.stdout else "")
if result.stderr:
    log(result.stderr[-1000:])
if result.returncode == 0:
    log("[OK] All dependencies installed successfully.")
else:
    log(f"[!] pip install returned code {result.returncode}")

log("\n" + "=" * 60)
log("  Setup complete! Check above for any errors.")
log("  Next: double-click run_mobile.bat to start the app.")
log("=" * 60)
