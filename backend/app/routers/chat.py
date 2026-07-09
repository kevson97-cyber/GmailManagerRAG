"""
routers/chat.py — Agent chat endpoint (SSE): native Ollama tool calling with a
confirm-before-destructive-action gate.

See app/agent/engine.py for the loop + event contract and app/agent/tools.py
for the tool registry and the resolve/execute split behind the confirmation
gate.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sse_starlette.sse import EventSourceResponse

from .. import deps
from ..agent.engine import run_agent
from ..agent.tools import ToolContext
from ..auth import require_token
from ..models import ChatRequest

router = APIRouter(tags=["chat"], dependencies=[Depends(require_token)])

# Keeps the SSE connection alive through Cloudflare Tunnel / proxy idle timeouts.
PING_INTERVAL_SECONDS = 15


@router.post("/api/chat")
async def chat(body: ChatRequest) -> EventSourceResponse:
    """
    Stream one agent turn as SSE. `messages` starts/continues a conversation;
    `confirm_token` (+ `cancelled`) resumes a turn that paused on a destructive
    action's confirmation. At least one of the two must be present.
    """
    if not body.messages and not body.confirm_token:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="messages must be non-empty unless resuming with confirm_token",
        )

    gmail = await asyncio.to_thread(deps.get_gmail)
    vs = await asyncio.to_thread(deps.get_vector_store)
    ctx = ToolContext(gmail=gmail, vs=vs)

    # Whitelist roles: clients may only speak as user/assistant. Injected
    # "system"/"tool" entries could fake tool results or override the system
    # prompt, so they are dropped before the transcript reaches the engine.
    messages = [
        {"role": m.role, "content": m.content}
        for m in body.messages
        if m.role in ("user", "assistant")
    ]
    if not messages and not body.confirm_token:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="messages must contain at least one user/assistant message",
        )

    async def event_gen():
        async for event_name, data in run_agent(messages, body.confirm_token, body.cancelled, ctx):
            yield {"event": event_name, "data": json.dumps(data)}

    return EventSourceResponse(event_gen(), ping=PING_INTERVAL_SECONDS)
