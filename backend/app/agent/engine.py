"""
engine.py — Ollama native tool-calling loop with a confirm-before-destructive
gate. See app/agent/tools.py for the tool registry and the resolve/execute
split, app/agent/prompts.py for the system prompt.

Event contract (yielded as (event_name, data) pairs; routers/chat.py maps
these 1:1 onto SSE `event:`/`data:` frames):
    token       {text}
    tool_call   {name, arguments}
    tool_result {name, summary}
    confirm     {confirm_token, action, description, count, preview}
    done        {finish_reason: "stop" | "awaiting_confirmation"}
    error       {message}

Confirmation protocol: a destructive tool call is only ever RESOLVED (preview,
no mutation) during the normal loop; the resolved payload is stashed in the
in-memory _PENDING store under a fresh token and a `confirm` + `done
(awaiting_confirmation)` pair is emitted, then run_agent returns — nothing
executes. The caller resumes by POSTing the same conversation again with
`confirm_token` (+ `cancelled`); only that code path ever calls
tools.execute_destructive_tool(), and only with the frozen payload pulled
back out of _PENDING (never re-resolved, never fed live model args).
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator

import ollama

from .. import config, ollama_status
from . import tools
from .prompts import build_system_prompt
from .tools import ToolContext

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5
MAX_HISTORY_TURNS = 12  # ~user+assistant pairs kept from the client transcript
PENDING_TTL_SECONDS = 600


# ── Pending confirmation store ──────────────────────────────────────────────────

@dataclass
class PendingAction:
    tool: str
    args: dict            # raw arguments the model called the tool with (for transcript replay)
    resolved: dict         # frozen preview payload from tools.resolve_destructive_tool()
    created_at: float = field(default_factory=time.time)


_PENDING: dict[str, PendingAction] = {}


def _purge_expired() -> None:
    now = time.time()
    for token in [t for t, p in _PENDING.items() if now - p.created_at > PENDING_TTL_SECONDS]:
        _PENDING.pop(token, None)


# ── Qwen3 <think> block stripping (streaming-safe) ──────────────────────────────

class _ThinkStripper:
    """
    Removes <think>...</think> spans from a stream of text chunks, even when a
    tag is split across chunk boundaries. Think content is discarded, never
    yielded as a token.
    """
    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    @staticmethod
    def _partial_suffix_len(buf: str, tag: str) -> int:
        """Length of the longest suffix of buf that is a (strict) prefix of tag."""
        max_check = min(len(buf), len(tag) - 1)
        for length in range(max_check, 0, -1):
            if tag.startswith(buf[-length:]):
                return length
        return 0

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        out: list[str] = []

        while True:
            if not self._in_think:
                idx = self._buf.find(self.OPEN)
                if idx != -1:
                    out.append(self._buf[:idx])
                    self._buf = self._buf[idx + len(self.OPEN):]
                    self._in_think = True
                    continue
                keep = self._partial_suffix_len(self._buf, self.OPEN)
                if keep:
                    out.append(self._buf[:-keep])
                    self._buf = self._buf[-keep:]
                else:
                    out.append(self._buf)
                    self._buf = ""
                break
            else:
                idx = self._buf.find(self.CLOSE)
                if idx != -1:
                    self._buf = self._buf[idx + len(self.CLOSE):]
                    self._in_think = False
                    continue
                keep = self._partial_suffix_len(self._buf, self.CLOSE)
                self._buf = self._buf[-keep:] if keep else ""
                break

        return "".join(out)

    def flush(self) -> str:
        """Call once the stream ends. Emits any trailing plain text; drops an unclosed think block."""
        if self._in_think:
            self._buf = ""
            return ""
        remainder, self._buf = self._buf, ""
        return remainder


def _one_line(text: str, limit: int = 200) -> str:
    line = " ".join((text or "").split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _truncate_history(messages: list[dict], max_turns: int) -> list[dict]:
    limit = max_turns * 2  # user+assistant pairs -> message count
    kept = messages[-limit:] if len(messages) > limit else messages
    # Never start the window on an orphaned tool result — some models reject a
    # role:"tool" message without its preceding assistant tool_call.
    while kept and kept[0].get("role") == "tool":
        kept = kept[1:]
    return kept


# ── Main loop ────────────────────────────────────────────────────────────────────

async def run_agent(
    messages: list[dict],
    confirm_token: str | None,
    cancelled: bool,
    ctx: ToolContext,
) -> AsyncGenerator[tuple[str, dict], None]:
    _purge_expired()

    working: list[dict] = [dict(m) for m in messages]

    # ── Resume from a paused confirmation ───────────────────────────────────
    if confirm_token:
        pending = _PENDING.pop(confirm_token, None)
        if pending is None:
            yield "error", {"message": "Confirmation expired — please ask again."}
            return

        if cancelled:
            result_text = "User declined the action."
        else:
            result_text = await asyncio.to_thread(
                tools.execute_destructive_tool, pending.tool, pending.resolved, ctx
            )

        working.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": pending.tool, "arguments": pending.args}}],
        })
        working.append({"role": "tool", "tool_name": pending.tool, "content": result_text})
        yield "tool_result", {"name": pending.tool, "summary": _one_line(result_text)}

    # ── Connectivity check (actionable error before we ever stream) ────────
    ollama_ok, ollama_hint = await asyncio.to_thread(ollama_status.is_available)
    if not ollama_ok:
        yield "error", {"message": ollama_hint}
        return

    index_count = await asyncio.to_thread(ctx.vs.count)
    system_prompt = build_system_prompt(index_count, ctx.gmail.user_email, config.OLLAMA_MODEL)

    client = ollama.AsyncClient(host=config.OLLAMA_HOST)

    for _ in range(MAX_ITERATIONS):
        chat_messages = [{"role": "system", "content": system_prompt}, *_truncate_history(working, MAX_HISTORY_TURNS)]

        stripper = _ThinkStripper()
        content_parts: list[str] = []
        collected_tool_calls: list[dict] = []

        try:
            # think=True for thinking-capable model families: Ollama then
            # routes reasoning into the separate message.thinking field (which
            # we never read) and message.content stays clean. think=False is
            # NOT reliable — current qwen3 builds ignore the /no_think soft
            # switch and leak reasoning into content with an orphan </think>
            # tag. Omit the param entirely for non-thinking models (llama3.2),
            # which reject any `think` value. _ThinkStripper below remains the
            # safety net for tag-style leaks.
            stream = await client.chat(
                model=config.OLLAMA_MODEL,
                messages=chat_messages,
                tools=tools.TOOL_SCHEMAS,
                stream=True,
                **ollama_status.think_kwargs(),
            )
            async for chunk in stream:
                msg = chunk.message
                if msg is None:
                    continue
                if msg.content:
                    visible = stripper.feed(msg.content)
                    if visible:
                        content_parts.append(visible)
                        yield "token", {"text": visible}
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        collected_tool_calls.append({
                            "name": tc.function.name,
                            "arguments": dict(tc.function.arguments or {}),
                        })
            tail = stripper.flush()
            if tail:
                content_parts.append(tail)
                yield "token", {"text": tail}

        except (ollama.ResponseError, ollama.RequestError) as e:
            yield "error", {"message": f"Ollama error: {e}"}
            return
        except Exception as e:  # noqa: BLE001 — connection dropped mid-stream, etc.
            logger.exception("Ollama streaming failed")
            ok, hint = await asyncio.to_thread(ollama_status.is_available)
            yield "error", {"message": hint if not ok else f"Ollama request failed: {e}"}
            return

        if not collected_tool_calls:
            yield "done", {"finish_reason": "stop"}
            return

        working.append({
            "role": "assistant",
            "content": "".join(content_parts),
            "tool_calls": [
                {"function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in collected_tool_calls
            ],
        })

        paused = False
        for call in collected_tool_calls:
            name, args = call["name"], call["arguments"]
            yield "tool_call", {"name": name, "arguments": args}

            if name in tools.DESTRUCTIVE_TOOLS:
                resolved = await asyncio.to_thread(tools.resolve_destructive_tool, name, args, ctx)
                if isinstance(resolved, str):
                    # Resolve failed (bad args / no matches) — feed back, let the model retry.
                    working.append({"role": "tool", "tool_name": name, "content": resolved})
                    yield "tool_result", {"name": name, "summary": _one_line(resolved)}
                    continue

                token = uuid.uuid4().hex
                _PENDING[token] = PendingAction(tool=name, args=args, resolved=resolved)
                yield "confirm", {
                    "confirm_token": token,
                    "action": name,
                    "description": resolved.get("description", ""),
                    "count": resolved.get("count", 0),
                    "preview": resolved.get("preview", []),
                }
                yield "done", {"finish_reason": "awaiting_confirmation"}
                paused = True
                break
            else:
                result = await asyncio.to_thread(tools.execute_read_tool, name, args, ctx)
                result_text = result if isinstance(result, str) else json.dumps(result)
                working.append({"role": "tool", "tool_name": name, "content": result_text})
                yield "tool_result", {"name": name, "summary": _one_line(result_text)}

        if paused:
            return
        # else: loop again so the model can see the tool results and respond

    yield "token", {"text": "\n\n(Reached the tool-call limit for this turn.)"}
    yield "done", {"finish_reason": "stop"}
