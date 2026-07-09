@echo off
REM start.bat - one-click launcher for GmailManagerRAG.
REM
REM   start.bat          starts Ollama (if needed), the backend, and the
REM                      frontend, then opens the app in your browser.
REM   start.bat tunnel   same, plus a Cloudflare quick tunnel for phone access.
REM
REM Each service runs in its own window; close a window (or Ctrl+C in it) to
REM stop that service.

cd /d "%~dp0"
setlocal

REM ---- 1. Ollama ----------------------------------------------------------
curl -s -o nul --max-time 2 http://localhost:11434/api/version 2>nul
if not errorlevel 1 goto ollama_ok
where ollama >nul 2>nul
if errorlevel 1 (
    echo [!] Ollama is not installed. Get it from https://ollama.com and run:
    echo       ollama pull qwen3:4b
    pause
    exit /b 1
)
echo Starting Ollama...
start "Ollama" /min cmd /c "ollama serve"
:ollama_ok

REM ---- 2. Backend (run_backend.bat handles venv + dependency install) -----
start "GmailManagerRAG backend" /d "%~dp0backend" cmd /k .\run_backend.bat

REM ---- 3. Frontend ---------------------------------------------------------
if not exist frontend\node_modules (
    echo Installing frontend dependencies - first run only, takes a minute...
    pushd frontend
    call npm install
    popd
)
start "GmailManagerRAG frontend" /d "%~dp0frontend" cmd /k npm run dev

REM ---- 4. Optional Cloudflare tunnel for phone access ----------------------
if /i "%~1"=="tunnel" (
    start "Cloudflare tunnel" /d "%~dp0backend" cmd /k .\run_tunnel.bat
)

REM ---- 5. Wait until both services answer, then open the browser -----------
echo Waiting for the backend to come up...
set /a tries=0
:wait_backend
set /a tries+=1
if %tries% gtr 60 goto timed_out
ping -n 3 127.0.0.1 >nul
curl -s -o nul --max-time 2 http://127.0.0.1:8000/api/health 2>nul
if errorlevel 1 goto wait_backend

echo Waiting for the frontend to come up...
set /a tries=0
:wait_frontend
set /a tries+=1
if %tries% gtr 60 goto timed_out
ping -n 3 127.0.0.1 >nul
curl -s -o nul --max-time 2 http://localhost:3000 2>nul
if errorlevel 1 goto wait_frontend

start http://localhost:3000
echo.
echo App is running: http://localhost:3000
echo First time here? Click the gear icon and paste API_TOKEN from backend\.env
exit /b 0

:timed_out
echo [!] A service did not come up in time - check the backend/frontend windows for errors.
pause
exit /b 1
