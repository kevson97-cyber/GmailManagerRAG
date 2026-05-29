"""
Initialize git repo, stage all files, and make initial commit.
Run this once — then use GitHub Desktop to push.
"""
import subprocess, sys, shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG = BASE / "git_setup_log.txt"
lines = []

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE, **kw)
    lines.append(f"$ {' '.join(cmd)}")
    if r.stdout.strip(): lines.append(r.stdout.strip())
    if r.stderr.strip(): lines.append(r.stderr.strip())
    return r

# Remove broken .git if it exists
git_dir = BASE / ".git"
if git_dir.exists():
    shutil.rmtree(git_dir, ignore_errors=True)

# Find git executable
git = shutil.which("git") or r"C:\Program Files\Git\bin\git.exe"

run([git, "init", "-b", "main"])
run([git, "config", "user.name", "Kevin Johnson"])
run([git, "config", "user.email", "kevson97@gmail.com"])
run([git, "remote", "add", "origin", "https://github.com/kevson97-cyber/GmailManagerRAG.git"])
run([git, "add", "."])
run([git, "commit", "-m",
     "feat: complete Gmail RAG assistant\n\n"
     "- Merged dashboard + sync page\n"
     "- Auto Gmail reconnect on startup\n"
     "- Label-based email deletion (CATEGORY_SOCIAL etc.)\n"
     "- Voice input via st.audio_input + SpeechRecognition\n"
     "- Compact mobile-first UI with button animations\n"
     "- Deletion cap raised to 1500, sync cap to 1500\n"
     "- Category filter buttons on sync page\n"
     "- Fixed restart script to kill pythonw.exe processes"])

LOG.write_text("\n".join(lines), encoding="utf-8")
(BASE / "git_setup_done.txt").write_text("done", encoding="utf-8")
