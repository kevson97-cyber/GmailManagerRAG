"""
gmail_client.py — Gmail API wrapper for reading, labelling, and filtering emails.
"""
import base64
import json
import re
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import GMAIL_SCOPES, CREDENTIALS_FILE, TOKEN_FILE


class GmailClient:
    """Authenticated Gmail API client."""

    def __init__(self):
        self.service = None
        self.user_email: str = ""
        self._authenticated: bool = False

    # ── Auth ──────────────────────────────────────────────────────────────────

    def authenticate(self) -> bool:
        """Run OAuth2 flow and store token. Opens browser on first run."""
        creds: Optional[Credentials] = None

        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GMAIL_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CREDENTIALS_FILE.exists():
                    raise FileNotFoundError(
                        f"credentials.json not found at {CREDENTIALS_FILE}.\n"
                        "Download it from Google Cloud Console → APIs & Services → Credentials."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)

            TOKEN_FILE.write_text(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)
        profile = self.service.users().getProfile(userId="me").execute()
        self.user_email = profile.get("emailAddress", "")
        self._authenticated = True
        return True

    def is_authenticated(self) -> bool:
        return self._authenticated and self.service is not None

    def disconnect(self):
        """Revoke stored token and reset client."""
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        self.service = None
        self.user_email = ""
        self._authenticated = False

    # ── Reading ───────────────────────────────────────────────────────────────

    def get_message_ids(self, max_results: int = 500, query: str = "") -> list[dict]:
        """Return a list of {id, threadId} dicts up to max_results."""
        self._require_auth()
        messages: list[dict] = []
        page_token: Optional[str] = None

        while len(messages) < max_results:
            batch_size = min(100, max_results - len(messages))
            params: dict = {"userId": "me", "maxResults": batch_size}
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token

            result = self.service.users().messages().list(**params).execute()
            batch = result.get("messages", [])
            if not batch:
                break
            messages.extend(batch)
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return messages

    def get_message_detail(self, message_id: str) -> Optional[dict]:
        """Fetch and parse a single email by ID. Returns None on error."""
        self._require_auth()
        try:
            raw = self.service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()
            return self._parse_message(raw)
        except HttpError:
            return None

    def _parse_message(self, msg: dict) -> dict:
        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        date_raw = headers.get("date", "")
        try:
            from email.utils import parsedate_to_datetime
            date = parsedate_to_datetime(date_raw).isoformat() if date_raw else ""
        except Exception:
            date = date_raw

        body = self._extract_body(msg.get("payload", {}))

        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId", ""),
            "subject": headers.get("subject", "(no subject)"),
            "sender": headers.get("from", ""),
            "recipient": headers.get("to", ""),
            "date": date,
            "snippet": msg.get("snippet", ""),
            "body": body[:3000],
            "labels": msg.get("labelIds", []),
        }

    def _extract_body(self, payload: dict) -> str:
        """Recursively pull plain-text (or de-tagged HTML) from payload."""
        body = ""

        def walk(part):
            nonlocal body
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    return True
            elif mime == "text/html" and not body:
                data = part.get("body", {}).get("data", "")
                if data:
                    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    body = re.sub(r"<[^>]+>", " ", html)
                    body = re.sub(r"\s+", " ", body).strip()
            for sub in part.get("parts", []):
                if walk(sub):
                    return True
            return False

        walk(payload)
        return body.strip()

    # ── Labels ────────────────────────────────────────────────────────────────

    # Gmail's full allowed background-color palette (as of 2024).
    # Text color must be either #ffffff or #000000.
    _GMAIL_BG_COLORS = [
        "#000000", "#434343", "#666666", "#999999", "#b7b7b7", "#cccccc", "#d9d9d9", "#ffffff",
        "#fb4c2f", "#ffad47", "#fad165", "#16a766", "#43d692", "#4a86e8", "#a479e2", "#f691b3",
        "#f6c5be", "#ffe6c7", "#fef1d1", "#b9e4d0", "#c6f3de", "#c9daf8", "#e4d7f5", "#fcdee8",
        "#efa093", "#ffd6a2", "#fce8b3", "#89d3b2", "#a0eac9", "#a4c2f4", "#d0bcf1", "#fbc8d4",
        "#e66550", "#ffbc6b", "#fcda83", "#44b984", "#68dfa9", "#6d9eeb", "#b694e8", "#f7a7c0",
        "#cc3a21", "#eaa041", "#f2c960", "#149e60", "#3dc789", "#3c78d8", "#8e63ce", "#e07798",
        "#ac2b16", "#cf8933", "#d5ae49", "#0b804b", "#2a9c68", "#285bac", "#653e9b", "#b65775",
        "#822111", "#a46a21", "#aa8831", "#076239", "#1a764d", "#1c4587", "#41236d", "#83334c",
    ]

    @classmethod
    def _nearest_gmail_color(cls, hex_color: str) -> tuple[str, str]:
        """
        Snap an arbitrary hex color to the nearest color in Gmail's allowed
        palette using RGB Euclidean distance.
        Returns (bg_color, text_color) where text is #ffffff or #000000.
        """
        def _parse(h: str) -> tuple[int, int, int]:
            h = h.lstrip("#")
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

        try:
            r, g, b = _parse(hex_color)
        except Exception:
            return "#16a766", "#ffffff"  # safe default

        best = min(
            cls._GMAIL_BG_COLORS,
            key=lambda c: sum((a - b_) ** 2 for a, b_ in zip(_parse(c), (r, g, b))),
        )
        # Choose white or black text based on relative luminance
        br, bg, bb = _parse(best)
        luminance = (0.299 * br + 0.587 * bg + 0.114 * bb) / 255
        text = "#000000" if luminance > 0.5 else "#ffffff"
        return best, text

    def get_labels(self) -> list[dict]:
        self._require_auth()
        return self.service.users().labels().list(userId="me").execute().get("labels", [])

    def create_label(self, name: str, bg_color: str = "#16a766", text_color: str = "#ffffff") -> dict:
        """Create a user label. Snaps bg_color to Gmail's allowed palette automatically."""
        self._require_auth()
        bg_color, text_color = self._nearest_gmail_color(bg_color)
        body = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
            "color": {"backgroundColor": bg_color, "textColor": text_color},
        }
        return self.service.users().labels().create(userId="me", body=body).execute()

    def apply_label(self, message_id: str, label_id: str):
        """Add a label to a single message."""
        self._require_auth()
        self.service.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": [label_id]}
        ).execute()

    # ── Deletion ──────────────────────────────────────────────────────────────

    def trash_email(self, message_id: str) -> None:
        """Move a single message to Trash (recoverable)."""
        self._require_auth()
        self.service.users().messages().trash(userId="me", id=message_id).execute()

    def trash_emails(self, message_ids: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
        """
        Move multiple messages to Trash.

        Returns:
            trashed_ids  : IDs of messages confirmed moved to Trash
            errors       : list of (id, error_message) for failures
        """
        self._require_auth()
        trashed: list[str] = []
        errors: list[tuple[str, str]] = []

        for mid in message_ids:
            try:
                result = self.service.users().messages().trash(
                    userId="me", id=mid
                ).execute()
                # Confirm the TRASH label is present in the response
                if "TRASH" in result.get("labelIds", []):
                    trashed.append(mid)
                else:
                    errors.append((mid, "API returned 200 but TRASH label not found"))
            except HttpError as e:
                errors.append((mid, f"API error {e.resp.status}: {e.error_details}"))
            except Exception as e:
                errors.append((mid, str(e)))

        return trashed, errors

    # ── Filters ───────────────────────────────────────────────────────────────

    def get_filters(self) -> list[dict]:
        self._require_auth()
        return (
            self.service.users()
            .settings()
            .filters()
            .list(userId="me")
            .execute()
            .get("filter", [])
        )

    def create_filter(self, criteria: dict, action: dict) -> dict:
        """
        criteria keys: from, to, subject, query, hasAttachment, excludeChats, size, sizeComparison
        action keys: addLabelIds, removeLabelIds, forward
        """
        self._require_auth()
        return (
            self.service.users()
            .settings()
            .filters()
            .create(userId="me", body={"criteria": criteria, "action": action})
            .execute()
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require_auth(self):
        if not self.is_authenticated():
            raise RuntimeError("GmailClient is not authenticated. Call authenticate() first.")
