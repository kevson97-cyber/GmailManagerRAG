@echo off
REM run_tunnel.bat - expose the local backend to the internet via a free
REM Cloudflare "quick tunnel" (no account needed).
REM
REM Prints a https://<random>.trycloudflare.com URL. Paste that URL into the
REM frontend's Settings sheet (gear icon) as the Backend URL - on your phone
REM too. The URL changes every time this script restarts; for a stable URL,
REM set up a named tunnel (see README.md, "Remote access").
REM
REM Install cloudflared once with:  winget install Cloudflare.cloudflared

where cloudflared >nul 2>nul
if errorlevel 1 (
    echo cloudflared is not installed. Install it with:
    echo   winget install Cloudflare.cloudflared
    exit /b 1
)

echo Starting Cloudflare quick tunnel to http://localhost:8000 ...
echo (Copy the https://*.trycloudflare.com URL below into the app's Settings.)
cloudflared tunnel --url http://localhost:8000
