@echo off
title GmailRAG - Setup
cd /d "%~dp0"

echo ============================================================
echo  GmailManagerRAG - Automated Setup
echo ============================================================
echo.

REM ── 1. Check Ollama ─────────────────────────────────────────
echo [1/3] Checking Ollama...
ollama --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Ollama not in PATH. Trying known location...
    "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" --version >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo [!] Cannot find ollama.exe. Please open Ollama from Start Menu and re-run this script.
        goto SKIP_OLLAMA
    ) else (
        set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
        echo [OK] Found Ollama at: %LOCALAPPDATA%\Programs\Ollama\ollama.exe
    )
) else (
    set "OLLAMA_EXE=ollama"
    echo [OK] Ollama is in PATH.
)

echo [  ] Checking for llama3.2 model...
%OLLAMA_EXE% list 2>&1 | findstr /i "llama3.2" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [  ] Pulling llama3.2 (~2GB - this will take a few minutes)...
    %OLLAMA_EXE% pull llama3.2
    if %ERRORLEVEL% NEQ 0 (
        echo [!] Failed to pull llama3.2. Make sure Ollama app is running and try again.
    ) else (
        echo [OK] llama3.2 model ready.
    )
) else (
    echo [OK] llama3.2 model already installed.
)
:SKIP_OLLAMA

REM ── 2. Create .env ──────────────────────────────────────────
echo.
echo [2/3] Setting up .env file...
if not exist ".env" (
    copy ".env.example" ".env" >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [OK] Created .env from .env.example
    ) else (
        echo [!] Could not copy .env.example - please do it manually
    )
) else (
    echo [OK] .env already exists.
)

REM ── 3. Install Python deps ──────────────────────────────────
echo.
echo [3/3] Installing Python dependencies...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Python not found. Please install Python from python.org
    goto DONE
)
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [!] pip install encountered errors. Check output above.
) else (
    echo [OK] All dependencies installed.
)

:DONE
echo.
echo ============================================================
echo  Setup complete!
echo  Next step: double-click run_mobile.bat to launch the app.
echo ============================================================
echo.
pause
