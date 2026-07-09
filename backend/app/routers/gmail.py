"""
routers/gmail.py — Gmail OAuth connect/disconnect and label/filter listing.

Supports both OAuth client types in credentials.json:
- "installed" (Desktop app): google-auth-oauthlib's run_local_server flow on a
  random localhost port, launched in a background thread.
- "web" (Web application): the backend itself serves the registered redirect
  URI (GET /auth/callback), exchanges the code, and saves token.json. The
  registered redirect must point at this server, e.g.
  http://localhost:8000/auth/callback.
"""
import asyncio
import json
import logging
import os
import secrets as _secrets
import threading
import webbrowser

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import Flow

from .. import config, deps
from ..auth import require_token
from ..models import ConnectResponse, LabelOut

# Google may report granted scopes in a different order / superset (e.g. it
# appends previously granted scopes); don't hard-fail the exchange on that.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gmail", tags=["gmail"], dependencies=[Depends(require_token)])

# Unauthenticated router: Google's browser redirect cannot carry our bearer
# header. The callback is protected by the single-use state token instead.
callback_router = APIRouter(tags=["gmail"])

# Guards against launching two interactive OAuth flows at once (double-click,
# retry from the phone while the PC browser tab is still open, etc.).
_oauth_flow_lock = threading.Lock()
_oauth_flow_running = False

# Pending web flow, single-use: the CSRF state token AND the Flow object
# itself. The same Flow must perform both authorization_url() and
# fetch_token() — it holds the PKCE code_verifier Google requires at exchange.
_web_flow_state: dict = {"state": None, "flow": None}


def _client_type() -> str:
    """'web' or 'installed', from the top-level key of credentials.json."""
    try:
        data = json.loads(config.CREDENTIALS_FILE.read_text())
        return "web" if "web" in data else "installed"
    except (OSError, json.JSONDecodeError):
        return "installed"


def _web_redirect_uri() -> str:
    data = json.loads(config.CREDENTIALS_FILE.read_text())
    uris = data.get("web", {}).get("redirect_uris", [])
    if not uris:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                "credentials.json is a web OAuth client but has no redirect_uris. "
                "Add http://localhost:8000/auth/callback in Google Cloud Console, "
                "or use a Desktop-app client instead."
            ),
        )
    return uris[0]


def _start_web_flow() -> None:
    """Open the Google consent page for a web-type client; the backend's own
    /auth/callback route finishes the exchange."""
    redirect_uri = _web_redirect_uri()
    flow = Flow.from_client_secrets_file(
        str(config.CREDENTIALS_FILE), scopes=config.GMAIL_SCOPES, redirect_uri=redirect_uri
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",  # needed to receive a refresh token
        prompt="consent",
    )
    _web_flow_state["state"] = state
    _web_flow_state["flow"] = flow
    webbrowser.open(auth_url)


def _run_installed_oauth(client) -> None:
    """Run the blocking run_local_server consent flow; always clear the flag."""
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

    Slow path: no usable token on disk. A Google consent page opens in a
    browser ON THIS PC (web flow or desktop flow depending on the client type
    in credentials.json); we return `needs_desktop_auth: true` right away.
    The frontend should tell the user to finish sign-in at the PC and poll
    /api/status until gmail.connected flips to true.
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

    if _client_type() == "web":
        await asyncio.to_thread(_start_web_flow)
        return ConnectResponse(connected=False, email="", needs_desktop_auth=True)

    with _oauth_flow_lock:
        if not _oauth_flow_running:
            _oauth_flow_running = True
            threading.Thread(
                target=_run_installed_oauth, args=(client,), daemon=True
            ).start()

    return ConnectResponse(connected=False, email="", needs_desktop_auth=True)


@callback_router.get("/auth/callback", include_in_schema=False)
async def oauth_callback(code: str = "", state: str = "", error: str = "") -> HTMLResponse:
    """Google redirects here after consent (web-type client only)."""
    page = (
        "<html><body style='font-family:sans-serif;background:#0f172a;color:#e2e8f0;"
        "display:flex;align-items:center;justify-content:center;height:100vh'>"
        "<div style='text-align:center'><h2>{title}</h2><p>{body}</p></div></body></html>"
    )

    expected = _web_flow_state.get("state")
    flow = _web_flow_state.get("flow")
    _web_flow_state["state"] = None  # single-use, success or not
    _web_flow_state["flow"] = None

    if error:
        return HTMLResponse(page.format(title="Sign-in cancelled", body=f"Google reported: {error}. You can close this tab and try again."))
    if not code or not expected or flow is None or not _secrets.compare_digest(state, expected):
        return HTMLResponse(
            page.format(title="Sign-in link expired", body="Go back to the app and click Connect Gmail again."),
            status_code=http_status.HTTP_400_BAD_REQUEST,
        )

    def _exchange() -> None:
        flow.fetch_token(code=code)
        config.TOKEN_FILE.write_text(flow.credentials.to_json())

    try:
        await asyncio.to_thread(_exchange)
    except Exception:
        logger.exception("OAuth code exchange failed")
        return HTMLResponse(
            page.format(title="Sign-in failed", body="The code exchange with Google failed. Check the backend window for details and try again."),
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    deps.reset_gmail()  # next /api/status silently logs in with the new token
    return HTMLResponse(page.format(title="Gmail connected ✓", body="You can close this tab and return to the app."))


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
