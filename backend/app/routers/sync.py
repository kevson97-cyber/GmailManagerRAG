"""
routers/sync.py — Sync job control (start/cancel) and progress streaming (SSE).

See app/sync_manager.py for the job model and the SSE event schema.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sse_starlette.sse import EventSourceResponse

from .. import config, deps
from ..auth import require_token
from ..models import SyncStartRequest, SyncStartResponse

router = APIRouter(prefix="/api/sync", tags=["sync"], dependencies=[Depends(require_token)])

# How often EventSourceResponse sends a keepalive comment while no real event
# is due — keeps the connection alive through Cloudflare Tunnel / proxy idle
# timeouts (see plan risk: "Cloudflare buffering/idle timeout on SSE").
PING_INTERVAL_SECONDS = 15


@router.post("/start", response_model=SyncStartResponse, status_code=http_status.HTTP_202_ACCEPTED)
async def start_sync(body: SyncStartRequest) -> SyncStartResponse:
    """Kick off a background Gmail → Chroma sync job. 409 if one is already running."""
    gmail = await asyncio.to_thread(deps.get_gmail)
    if not gmail.is_authenticated():
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Gmail is not connected"
        )

    max_emails = max(1, min(body.max_emails, config.MAX_EMAILS_PER_SYNC))

    manager = deps.get_sync_manager()
    try:
        job_id = await manager.start(max_emails, body.query, body.categories)
    except RuntimeError as e:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=str(e))

    return SyncStartResponse(job_id=job_id)


@router.get("/progress")
async def sync_progress() -> EventSourceResponse:
    """
    SSE stream of sync progress events (event name "progress", JSON data).

    Replays the current/most-recent job's full history on connect (so a page
    refresh or a late subscriber still sees prior progress), then streams new
    events until a terminal one (done/error/cancelled) ends the stream.
    """
    manager = deps.get_sync_manager()

    async def event_gen():
        async for event in manager.subscribe():
            yield {"event": "progress", "data": json.dumps(event)}

    return EventSourceResponse(event_gen(), ping=PING_INTERVAL_SECONDS)


@router.post("/cancel")
async def cancel_sync() -> dict:
    """Request cancellation of the running sync job. Idempotent — 200 either way."""
    manager = deps.get_sync_manager()
    cancelled = await manager.cancel()
    return {"cancelled": cancelled}
