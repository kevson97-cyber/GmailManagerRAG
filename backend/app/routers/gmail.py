"""
routers/gmail.py — Gmail OAuth connect/disconnect and label/filter listing.
"""
import asyncio
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status

from .. import config, deps
from ..auth import require_token
from ..models import ConnectResponse, LabelOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gmail", tags=["gmail"], dependencies=[Depends(require_token)])

# Guards against launching two interactive OAuth flows at once (double-click,
# retry from the phone while the PC browser tab is still open, etc.).
_oauth_flow_lock = threading.Lock()
_oauth_flow_running = False


def _run_interactive_oauth(client) -> None:
    """Run the blocking browser consent flow; always clear the running flag."""
    global _oauth_flow_running
    try:
        client.authenticate()
    except Exception:
        logger.exception("Interactive Gmail OAuth flow failed")
    finally:
        with _oauth_flow_lock:
            _oauth_flow_running = False


@router.post("/connect", response_model=ConnectResponse)
async def connect() -> ConnectResponse:
    """
    Authenticate with Gmail.

    Fast path: backend/credentials/token.json already holds a valid (or
    refreshable) token — returns connected immediately.

    Slow path: no usable token on disk. The Google consent flow
    (`flow.run_local_server()`) blocks and opens a browser window ON THIS PC,
    so we launch it in a daemon thread and return `needs_desktop_auth: true`
    right away instead of holding the HTTP request open. The frontend should
    tell the user to finish sign-in at the PC and poll /api/status until
    gmail.connected flips to true.
    """
    global _oauth_flow_running

    if not config.CREDENTIALS_FILE.exists():
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                "credentials.json not found. Download OAuth client credentials "
                f"from Google Cloud Console and save them to {config.CREDENTIALS_FILE}"
            ),
        )

    client = await asyncio.to_thread(deps.get_gmail)
    if client.is_authenticated():
        return ConnectResponse(connected=True, email=client.user_email, needs_desktop_auth=False)

    with _oauth_flow_lock:
        if not _oauth_flow_running:
            _oauth_flow_running = True
            threading.Thread(
                target=_run_interactive_oauth, args=(client,), daemon=True
            ).start()

    return ConnectResponse(connected=False, email="", needs_desktop_auth=True)


@router.post("/disconnect", response_model=ConnectResponse)
async def disconnect() -> ConnectResponse:
    """Revoke the stored token and drop the cached GmailClient singleton."""
    client = await asyncio.to_thread(deps.get_gmail)
    await asyncio.to_thread(client.disconnect)
    deps.reset_gmail()
    return ConnectResponse(connected=False, email="", needs_desktop_auth=False)


@router.get("/labels", response_model=list[LabelOut])
async def list_labels() -> list[LabelOut]:
    client = await asyncio.to_thread(deps.get_gmail)
    if not client.is_authenticated():
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Gmail is not connected")
    raw = await asyncio.to_thread(client.get_labels)
    return [
        LabelOut(id=label.get("id", ""), name=label.get("name", ""), type=label.get("type", ""))
        for label in raw
    ]


@router.get("/filters")
async def list_filters() -> list[dict]:
    client = await asyncio.to_thread(deps.get_gmail)
    if not client.is_authenticated():
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Gmail is not connected")
    return await asyncio.to_thread(client.get_filters)
