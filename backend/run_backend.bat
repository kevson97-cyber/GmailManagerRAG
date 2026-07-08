@echo off
REM run_backend.bat — set up the venv (if needed) and start the FastAPI backend.
REM Must be run from the backend\ directory (double-click or `cd backend && run_backend.bat`).

cd /d "%~dp0"

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo Python 3.10 or newer is required. Found:
    python --version
    exit /b 1
)

if not exist venv\.deps_installed (
    echo Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Dependency install failed.
        exit /b 1
    )
    type nul > venv\.deps_installed
)

echo Starting GmailManagerRAG backend on http://127.0.0.1:8000 ...
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
