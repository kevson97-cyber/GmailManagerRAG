@echo off
title Gmail RAG Assistant
cd /d "%~dp0"

echo ============================================
echo   Gmail RAG Assistant — Starting...
echo ============================================
echo.

REM Check if .env exists
if not exist ".env" (
    echo [WARN] .env file not found.
    echo        Copy .env.example to .env and add your ANTHROPIC_API_KEY first.
    echo.
    pause
    exit /b 1
)

REM Check if credentials.json exists
if not exist "credentials\credentials.json" (
    echo [WARN] credentials\credentials.json not found.
    echo        Download it from Google Cloud Console and place it there.
    echo.
    pause
    exit /b 1
)

echo Opening http://localhost:8501 in your browser...
echo Press Ctrl+C in this window to stop the server.
echo.

python -m streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false

pause
