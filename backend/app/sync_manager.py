"""
sync_manager.py — Background Gmail → ChromaDB sync job (single job at a time).

This app is single-user/single-tab, so the model is deliberately simple: at
most one sync job runs at a time (`start()` raises if one is already active),
and progress is an append-only list of event dicts guarded by an
`asyncio.Condition`. Any number of SSE subscribers — including ones that
connect mid-job or reconnect after a dropped connection/page refresh — call
`subscribe()`, which replays the full event history for the most recent job
from index 0 and then waits for new events, ending after a terminal event.

Event schema (plain dict, JSON-encoded by routers/sync.py for SSE):
    {
        "job_id":   str | None,   # None only for the synthetic "idle" event
        "phase":    "idle" | "listing" | "fetching" | "embedding"
                    | "done" | "error" | "cancelled",
        "fetched":  int,          # messages fetched from Gmail so far
        "embedded": int,          # messages embedded (fetched batch fully processed)
        "total":    int,          # total message IDs matched by the query
        "added":    int,          # newly added (non-duplicate) rows in the vector store
        "message":  str | None,   # human-readable status / error / warning text
    }
"""
import asyncio
import logging
import uuid
from typing import Callable, Optional

from .gmail_client import GmailClient
from .vector_store import EmailVectorStore

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
TERMINAL_PHASES = {"done", "error", "cancelled"}
VALID_CATEGORIES = {"primary", "social", "promotions", "updates", "forums"}


def _build_query(query: str, categories: list[str]) -> str:
    """User query + one `category:<name>` term per requested category, space-joined."""
    terms = [query.strip()] if query and query.strip() else []
    terms.extend(f"category:{c}" for c in categories if c in VALID_CATEGORIES)
    return " ".join(terms)


class SyncManager:
    """Orchestrates one Gmail → Chroma sync job at a time."""

    def __init__(
        self,
        gmail_getter: Callable[[], GmailClient],
        vector_store_getter: Callable[[], EmailVectorStore],
    ):
        self._get_gmail = gmail_getter
        self._get_vector_store = vector_store_getter

        self._start_lock = asyncio.Lock()
        self._condition = asyncio.Condition()

        self._job_id: Optional[str] = None
        self._events: list[dict] = []
        self._running: bool = False
        self._cancel_requested: bool = False
        self._task: Optional[asyncio.Task] = None
        self._last_result: Optional[dict] = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def last_result(self) -> Optional[dict]:
        """Terminal event of the most recently completed job, if any."""
        return self._last_result

    # ── Start ─────────────────────────────────────────────────────────────────

    async def start(self, max_emails: int, query: str, categories: list[str]) -> str:
        """Launch a new sync job. Raises RuntimeError if one is already running."""
        async with self._start_lock:
            if self._running:
                raise RuntimeError("A sync job is already running")

            job_id = uuid.uuid4().hex
            self._job_id = job_id
            self._events = []
            self._cancel_requested = False
            self._running = True

            full_query = _build_query(query, categories)
            self._task = asyncio.create_task(self._run(job_id, max_emails, full_query))
            return job_id

    async def cancel(self) -> bool:
        """
        Request cancellation of the running job (idempotent).

        Returns True if a job was running (cancellation requested), False if
        there was nothing to cancel. The loop itself notices the flag at the
        next batch boundary and pushes the terminal "cancelled" event — this
        method does not push events directly.
        """
        async with self._condition:
            if not self._running:
                return False
            self._cancel_requested = True
            return True

    # ── Worker ────────────────────────────────────────────────────────────────

    async def _run(self, job_id: str, max_emails: int, query: str) -> None:
        fetched = embedded = added_total = total = 0
        fetch_errors = 0

        try:
            await self._emit(job_id, "listing", fetched, embedded, total, added_total,
                              "Listing message IDs…")

            gmail = await asyncio.to_thread(self._get_gmail)
            if not gmail.is_authenticated():
                await self._emit(job_id, "error", fetched, embedded, total, added_total,
                                  "Gmail is not connected")
                return

            vs = await asyncio.to_thread(self._get_vector_store)

            id_dicts = await asyncio.to_thread(gmail.get_message_ids, max_emails, query)
            message_ids = [d["id"] for d in id_dicts]
            total = len(message_ids)

            if self._cancel_requested:
                await self._emit(job_id, "cancelled", fetched, embedded, total, added_total,
                                  "Cancelled before fetching started")
                return

            await self._emit(job_id, "fetching", fetched, embedded, total, added_total,
                              f"Found {total} messages")

            for i in range(0, total, BATCH_SIZE):
                if self._cancel_requested:
                    await self._emit(job_id, "cancelled", fetched, embedded, total, added_total,
                                      "Cancelled")
                    return

                batch_ids = message_ids[i:i + BATCH_SIZE]
                batch_emails = await asyncio.to_thread(self._fetch_batch, gmail, batch_ids)

                fetched += len(batch_ids)
                fetch_errors += len(batch_ids) - len(batch_emails)

                await self._emit(
                    job_id, "fetching", fetched, embedded, total, added_total,
                    f"{fetch_errors} messages failed to fetch" if fetch_errors else None,
                )

                if self._cancel_requested:
                    await self._emit(job_id, "cancelled", fetched, embedded, total, added_total,
                                      "Cancelled")
                    return

                if batch_emails:
                    added = await asyncio.to_thread(vs.add_emails, batch_emails)
                    added_total += added
                embedded += len(batch_emails)

                await self._emit(job_id, "embedding", fetched, embedded, total, added_total)

            message = f"Synced {added_total} new emails"
            if fetch_errors:
                message += f" ({fetch_errors} messages failed to fetch)"
            await self._emit(job_id, "done", fetched, embedded, total, added_total, message)

        except Exception as e:  # noqa: BLE001 — surfaced to the client as an error event
            logger.exception("Sync job %s failed", job_id)
            await self._emit(job_id, "error", fetched, embedded, total, added_total, str(e))

    @staticmethod
    def _fetch_batch(gmail: GmailClient, ids: list[str]) -> list[dict]:
        """
        Fetch full details for a batch of message IDs.

        Failed messages are excluded and counted by the caller as fetch_errors.
        GmailClient.get_message_detail() only swallows HttpError, so transport
        blips (timeouts, connection resets) and parse failures are caught here
        too — one bad message must never abort a whole sync.
        """
        emails = []
        for mid in ids:
            try:
                detail = gmail.get_message_detail(mid)
            except Exception:  # noqa: BLE001 — counted as a fetch error, sync continues
                logger.warning("Fetch failed for message %s", mid, exc_info=True)
                detail = None
            if detail is not None:
                emails.append(detail)
        return emails

    # ── Events ────────────────────────────────────────────────────────────────

    async def _emit(
        self, job_id: str, phase: str, fetched: int, embedded: int, total: int,
        added: int, message: Optional[str] = None,
    ) -> None:
        event = {
            "job_id": job_id,
            "phase": phase,
            "fetched": fetched,
            "embedded": embedded,
            "total": total,
            "added": added,
            "message": message,
        }
        async with self._condition:
            self._events.append(event)
            if phase in TERMINAL_PHASES:
                self._running = False
                self._last_result = event
            self._condition.notify_all()

    # ── Subscribe (SSE) ──────────────────────────────────────────────────────

    async def subscribe(self):
        """
        Async generator yielding progress events for the most recent job.

        Replays the job's full event history from index 0 (covers subscribers
        that connect after the job started, or reconnect after a dropped
        connection/page refresh), then waits for new events as they arrive.
        Ends after yielding a terminal event. If no job has ever run, yields a
        single synthetic "idle" event and ends immediately.
        """
        async with self._condition:
            if self._job_id is None:
                yield {
                    "job_id": None, "phase": "idle", "fetched": 0, "embedded": 0,
                    "total": 0, "added": 0, "message": "No sync has run yet",
                }
                return
            # Snapshot the list object for the most recent job. If a new job
            # starts later, self._events is rebound to a fresh list in
            # start() — but that can only happen after this list already
            # received its terminal event (start() requires `not self._running`),
            # so continuing to read this same object is always safe/complete.
            events = self._events

        index = 0
        while True:
            async with self._condition:
                while index >= len(events):
                    await self._condition.wait()
                event = events[index]
                index += 1
            yield event
            if event["phase"] in TERMINAL_PHASES:
                return
