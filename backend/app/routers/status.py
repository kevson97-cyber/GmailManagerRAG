"""
routers/status.py — Liveness check (no auth) and aggregate status (auth).
"""
import asyncio

from fastapi import APIRouter, Depends

from .. import config, deps, ollama_status
from ..auth import require_token
from ..models import GmailStatus, IndexStatus, OllamaStatus, StatusResponse

router = APIRouter(tags=["status"])


@router.get("/api/health")
async def health() -> dict:
    """Unauthenticated liveness check — used by the frontend to detect a dead backend."""
    return {"ok": True, "version": "2.0.0"}


@router.get(
    "/api/status",
    response_model=StatusResponse,
    dependencies=[Depends(require_token)],
)
async def get_status() -> StatusResponse:
    """Aggregate gmail/ollama/index status for the frontend's ConnectionCard."""
    gmail_client = await asyncio.to_thread(deps.get_gmail)
    gmail_state = GmailStatus(
        connected=gmail_client.is_authenticated(),
        email=gmail_client.user_email,
    )

    ollama_ok, ollama_message = await asyncio.to_thread(ollama_status.is_available)
    ollama_state = OllamaStatus(available=ollama_ok, model=config.OLLAMA_MODEL, message=ollama_message)

    vs = await asyncio.to_thread(deps.get_vector_store)
    count = await asyncio.to_thread(vs.count)
    index_state = IndexStatus(count=count)

    return StatusResponse(gmail=gmail_state, ollama=ollama_state, index=index_state)
