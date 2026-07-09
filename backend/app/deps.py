"""
deps.py — Process-wide singletons (GmailClient, EmailVectorStore, SyncManager)
with lazy initialization guarded by locks.

GmailClient is silently reconnected from an existing backend/credentials/token.json
on first use (mirrors the old Streamlit app's "already logged in" experience),
but this module never runs the interactive OAuth flow itself — that only
happens inside POST /api/gmail/connect (see app/routers/gmail.py). If there is
no token on disk, or it can't be refreshed, the singleton is simply left
unauthenticated.
"""
import threading

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from . import config
from .gmail_client import GmailClient
from .sync_manager import SyncManager
from .vector_store import EmailVectorStore

# ── GmailClient singleton ─────────────────────────────────────────────────────

_gmail_lock = threading.Lock()
_gmail_client: GmailClient | None = None


def _try_silent_login(client: GmailClient) -> None:
    """Load token.json and build the Gmail service if possible. Never interactive."""
    if not config.TOKEN_FILE.exists():
        return

    try:
        creds = Credentials.from_authorized_user_file(str(config.TOKEN_FILE), config.GMAIL_SCOPES)

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                config.TOKEN_FILE.write_text(creds.to_json())
            else:
                return  # expired, unrefreshable — needs POST /api/gmail/connect

        client.service = build("gmail", "v1", credentials=creds)
        profile = client.service.users().getProfile(userId="me").execute()
        client.user_email = profile.get("emailAddress", "")
        client._authenticated = True
    except Exception:
        # Token missing/corrupt/revoked/network error — stay unauthenticated;
        # the caller falls back to the explicit connect endpoint.
        client.service = None
        client.user_email = ""
        client._authenticated = False


def get_gmail() -> GmailClient:
    """Return the process-wide GmailClient, silently reconnecting on first use."""
    global _gmail_client
    if _gmail_client is None:
        with _gmail_lock:
            if _gmail_client is None:
                client = GmailClient()
                _try_silent_login(client)
                _gmail_client = client
    return _gmail_client


def reset_gmail() -> None:
    """Drop the cached GmailClient so the next get_gmail() rebuilds it from scratch."""
    global _gmail_client
    with _gmail_lock:
        _gmail_client = None


# ── EmailVectorStore singleton ────────────────────────────────────────────────

_vs_lock = threading.Lock()
_vector_store: EmailVectorStore | None = None


def get_vector_store() -> EmailVectorStore:
    """Return the process-wide EmailVectorStore, creating it on first use."""
    global _vector_store
    if _vector_store is None:
        with _vs_lock:
            if _vector_store is None:
                _vector_store = EmailVectorStore()
    return _vector_store


# ── SyncManager singleton (Phase 2) ───────────────────────────────────────────
# Constructed with the getters (not the objects themselves) so it always
# reaches the current GmailClient/EmailVectorStore singleton, even across a
# disconnect/reconnect that swaps out the cached GmailClient (see reset_gmail).
_sync_lock = threading.Lock()
_sync_manager: SyncManager | None = None


def get_sync_manager() -> SyncManager:
    """Return the process-wide SyncManager, creating it on first use."""
    global _sync_manager
    if _sync_manager is None:
        with _sync_lock:
            if _sync_manager is None:
                _sync_manager = SyncManager(get_gmail, get_vector_store)
    return _sync_manager
