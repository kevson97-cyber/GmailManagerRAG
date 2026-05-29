"""Kill any running ngrok processes and tunnels."""
import subprocess, sys
# Kill via pyngrok
try:
    from pyngrok import ngrok
    ngrok.kill()
except Exception as e:
    pass
# Also kill via process name
subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], capture_output=True)
subprocess.run(["taskkill", "/F", "/IM", "ngrok"], capture_output=True)
