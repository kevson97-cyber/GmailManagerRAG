@echo off
title Install Dependencies — Gmail RAG Assistant
cd /d "%~dp0"

echo ============================================
echo   Installing Python dependencies...
echo ============================================
echo.
echo This may take a few minutes on first run.
echo (sentence-transformers downloads a ~90MB embedding model)
echo.
echo NOTE: This app uses Ollama for AI — make sure you have it installed:
echo   https://ollama.com
echo   Then run once in a terminal:  ollama pull llama3.2
echo.

pip install -r requirements.txt

echo.
echo ============================================
echo   Done! You can now run: run.bat
echo ============================================
echo.
pause
