"""Install SpeechRecognition silently then signal done."""
import subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
log = BASE / "install_sr_log.txt"

result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "SpeechRecognition", "--quiet"],
    capture_output=True, text=True,
)
log.write_text(result.stdout + result.stderr, encoding="utf-8")
(BASE / "install_sr_done.txt").write_text("done", encoding="utf-8")
