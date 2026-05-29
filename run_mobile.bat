@echo off
title Gmail RAG Assistant — Mobile Access
cd /d "%~dp0"

echo ============================================================
echo   Gmail RAG Assistant — Mobile / Remote Access
echo ============================================================
echo.

REM Check for .env
if not exist ".env" (
    echo [WARN] .env file not found.
    echo        Copy .env.example to .env and add your ANTHROPIC_API_KEY first.
    echo.
    pause
    exit /b 1
)

REM Check for credentials
if not exist "credentials\credentials.json" (
    echo [WARN] credentials\credentials.json not found.
    echo.
    pause
    exit /b 1
)

python run_mobile.py

pause
