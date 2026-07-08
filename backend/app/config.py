"""
config.py — Central configuration for GmailManagerRAG backend.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# BASE_DIR = backend/ (this file lives in backend/app/, so parent.parent is backend/)
BASE_DIR = Path(__file__).parent.parent

# Load .env file from backend/.env
load_dotenv(BASE_DIR / ".env")

CREDENTIALS_DIR = BASE_DIR / "credentials"
CHROMA_DIR = BASE_DIR / "chroma_db"

# Ensure directories exist
CREDENTIALS_DIR.mkdir(exist_ok=True)
CHROMA_DIR.mkdir(exist_ok=True)

# ── Gmail OAuth ─────────────────────────────────────────────────────────────
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://mail.google.com/",
]

CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"
TOKEN_FILE = CREDENTIALS_DIR / "token.json"

# ── Ollama (local LLM, no API key needed) ────────────────────────────────────
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")

# ── ChromaDB ─────────────────────────────────────────────────────────────────
CHROMA_COLLECTION_NAME = "gmail_emails"  # do not change — existing index compatibility

# ── Embeddings (local, free) ─────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ── Sync settings ─────────────────────────────────────────────────────────────
MAX_EMAILS_PER_SYNC = int(os.getenv("MAX_EMAILS_PER_SYNC", "500"))

# ── API auth ──────────────────────────────────────────────────────────────────
# Bearer token required on every route except /api/health. Must be set in
# backend/.env — an unset token fails the app closed (see app/auth.py).
API_TOKEN = os.getenv("API_TOKEN", "")

# ── CORS ──────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins, e.g. "http://localhost:3000,https://myapp.vercel.app"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
] or ["http://localhost:3000"]
