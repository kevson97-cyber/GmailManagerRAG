"""
models.py — Pydantic v2 request/response schemas for the API.

Defines shapes for all three backend phases up front so later routers
(sync, chat) can import from here without churn.
"""
from pydantic import BaseModel, Field


# ── Status (Phase 1) ──────────────────────────────────────────────────────────

class GmailStatus(BaseModel):
    connected: bool
    email: str = ""


class OllamaStatus(BaseModel):
    available: bool
    model: str
    message: str = ""


class IndexStatus(BaseModel):
    count: int


class StatusResponse(BaseModel):
    gmail: GmailStatus
    ollama: OllamaStatus
    index: IndexStatus


# ── Gmail (Phase 1) ───────────────────────────────────────────────────────────

class ConnectResponse(BaseModel):
    connected: bool
    email: str = ""
    needs_desktop_auth: bool = False
    # Web-flow consent URL; the frontend opens it (a cloud host has no display)
    auth_url: str = ""


class LabelOut(BaseModel):
    id: str
    name: str
    type: str = ""


# ── Sync (Phase 2) ────────────────────────────────────────────────────────────

class SyncStartRequest(BaseModel):
    max_emails: int = 500
    query: str = ""
    categories: list[str] = Field(default_factory=list)


class SyncStartResponse(BaseModel):
    job_id: str


# ── Emails / stats (Phase 2) ──────────────────────────────────────────────────

class EmailItem(BaseModel):
    id: str
    subject: str = ""
    sender: str = ""
    recipient: str = ""
    date: str = ""
    snippet: str = ""
    labels: list[str] = Field(default_factory=list)


class EmailListResponse(BaseModel):
    total: int
    items: list[EmailItem]


class StatsResponse(BaseModel):
    total_indexed: int
    unique_senders: int
    top_senders: list[tuple[str, int]]


# ── Chat / agent (Phase 3) ────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    confirm_token: str | None = None
    cancelled: bool = False
