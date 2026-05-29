"""Restart the GmailRAG app: kill existing processes, relaunch run_mobile_bg.pyw"""
import subprocess, sys, time, os
from pathlib import Path

BASE = Path(__file__).resolve().parent
URL_FILE = BASE / "mobile_url.txt"

# Kill ngrok
try:
    from pyngrok import ngrok
    ngrok.kill()
except Exception:
    pass
subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], capture_output=True)

# Kill ALL pythonw.exe and python.exe processes running app-related scripts
# (streamlit app.py, run_mobile_bg) — exclude ourselves
my_pid = str(os.getpid())
for proc_name in ("pythonw.exe", "python.exe"):
    result = subprocess.run(
        ["wmic", "process", "where", f"name='{proc_name}'",
         "get", "processid,commandline"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        line_lower = line.lower()
        is_target = (
            ("streamlit" in line_lower and "app.py" in line_lower)
            or "run_mobile_bg" in line_lower
        )
        if is_target and my_pid not in line:
            parts = line.strip().split()
            if parts:
                pid = parts[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)

URL_FILE.write_text("RESTARTING...\n", encoding="utf-8")
time.sleep(3)

# Relaunch run_mobile_bg.pyw
subprocess.Popen(
    [sys.executable, str(BASE / "run_mobile_bg.pyw")],
    cwd=BASE,
    creationflags=0x00000008,  # DETACHED_PROCESS
)
