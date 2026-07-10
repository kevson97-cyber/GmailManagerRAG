@echo off
REM start.bat - THE one command: sets up (first run) and starts GmailManagerRAG.
REM
REM   start.bat            setup if needed, then run; opens the app in your browser
REM   start.bat rebuild    force-rebuild the frontend, then run
REM   start.bat tunnel     also open a Cloudflare quick tunnel for phone access
REM
REM The server runs in THIS window (Ctrl+C to stop). Everything is served on
REM http://localhost:8000 - UI and API together.

cd /d "%~dp0"
setlocal

REM ---- 1. Python venv + backend dependencies -------------------------------
if not exist backend\venv (
    echo Creating Python virtual environment...
    py -3 -m venv backend\venv 2>nul || python -m venv backend\venv
    if not exist backend\venv (
        echo [!] Python 3.10+ is required. Install it from https://python.org
        pause
        exit /b 1
    )
)
backend\venv\Scripts\python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo [!] Python 3.10 or newer is required. Found:
    backend\venv\Scripts\python --version
    pause
    exit /b 1
)
if not exist backend\venv\.deps_installed (
    echo Installing backend dependencies - first run only...
    backend\venv\Scripts\python -m pip install -q -r backend\requirements.txt
    if errorlevel 1 (
        echo [!] Dependency install failed.
        pause
        exit /b 1
    )
    type nul > backend\venv\.deps_installed
)

REM ---- 2. backend\.env with a fresh API token on first run -----------------
if not exist backend\.env (
    for /f %%t in ('backend\venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(32))"') do set NEWTOKEN=%%t
    (
        echo API_TOKEN=%NEWTOKEN%
        echo OLLAMA_MODEL=qwen3:4b
    ) > backend\.env
    echo.
    echo Generated backend\.env - your API token ^(paste it in the app's Settings^):
    echo   %NEWTOKEN%
    echo.
)

REM ---- 3. Frontend build (static export served by the backend) -------------
if /i "%~1"=="rebuild" if exist frontend\out rmdir /s /q frontend\out
if not exist frontend\out\index.html (
    if not exist frontend\node_modules (
        echo Installing frontend dependencies - first run only...
        pushd frontend
        call npm ci
        popd
    )
    echo Building the frontend...
    pushd frontend
    call npm run build
    popd
    if not exist frontend\out\index.html (
        echo [!] Frontend build failed - check the output above.
        pause
        exit /b 1
    )
)

REM ---- 4. Ollama ------------------------------------------------------------
curl -s -o nul --max-time 2 http://localhost:11434/api/version 2>nul
if not errorlevel 1 goto ollama_ok
where ollama >nul 2>nul
if errorlevel 1 (
    echo [!] Ollama is not installed. Get it from https://ollama.com then run:
    echo       ollama pull qwen3:4b
    pause
    exit /b 1
)
echo Starting Ollama...
start "Ollama" /min cmd /c "ollama serve"
:ollama_ok

REM ---- 5. Optional Cloudflare quick tunnel (phone access) -------------------
if /i "%~1"=="tunnel" (
    where cloudflared >nul 2>nul
    if errorlevel 1 (
        echo [!] cloudflared not installed:  winget install Cloudflare.cloudflared
    ) else (
        echo Opening tunnel - the https://*.trycloudflare.com URL serves the whole app.
        start "Cloudflare tunnel" cmd /k cloudflared tunnel --url http://localhost:8000
    )
)

REM ---- 6. Open the browser once the server answers, then run the server ----
start "" /min cmd /c "for /l %%i in (1,1,60) do (curl -s -o nul --max-time 2 http://127.0.0.1:8000/api/health && start http://localhost:8000 && exit || ping -n 3 127.0.0.1 >nul)"
echo.
echo Starting GmailManagerRAG on http://localhost:8000  (Ctrl+C to stop)
backend\venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
