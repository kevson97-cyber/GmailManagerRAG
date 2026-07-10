"""
routines.py — Background routine that labels unimportant/generic inbox mail
with the Gmail label "Generic".

Runs every ROUTINE_INTERVAL_MINUTES while the server is up (FastAPI lifespan
starts scheduler_loop) and on demand via POST /api/routines/generic/run.
Classification is done by the local Ollama model in small batches, with a
conservative bias: when the model is unsure — or its output is unparsable —
nothing gets labeled.

Dedup: emails judged generic are excluded by the Gmail query itself
(-label:Generic); emails judged NOT generic are remembered in
backend/routine_state.json so they aren't re-classified every tick.
Note: index metadata for freshly labeled emails goes stale until the next
sync re-fetches them — accepted, the Sync page refreshes on resync.
"""
import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import ollama

from . import config, ollama_status
from .gmail_client import GmailClient

logger = logging.getLogger(__name__)

_MAX_REMEMBERED_IDS = 5000
_SNIPPET_LIMIT = 200

_CLASSIFY_PROMPT = """You are an email triage assistant. For each numbered email decide if it is \
GENERIC — mail a busy person would skip reading.

GENERIC (generic=true): promotions, marketing, sales offers, coupons, \
newsletters, digests, product announcements, mailing-list event invites, \
social-network activity blasts, surveys, generic fundraising or political mail.

NOT GENERIC (generic=false):
- personal mail from a real person
- work or business correspondence
- financial mail: bills, invoices, statements, payment requests
- anything that requires an action, reply, or decision
- automated transactional notifications: shipping/delivery updates, order \
confirmations, account alerts, security codes, password resets, \
appointment or booking reminders — never mark these generic
If you are unsure, answer false.

Emails:
{emails}

Respond with ONLY a JSON array like [{{"n":1,"generic":true}},{{"n":2,"generic":false}}], \
exactly one entry per email, no other text. Reminder: transactional \
notifications (shipping, order confirmations, security codes, alerts) are \
NOT generic."""


def _think_kwargs() -> dict:
    """Same gating as agent/engine.py: think=True only for thinking-capable
    families, so reasoning lands in message.thinking, not content."""
    if config.OLLAMA_MODEL.lower().startswith(("qwen3", "deepseek-r1")):
        return {"think": True}
    return {}


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


class GenericLabelRoutine:
    """Scan → classify → label pipeline plus its scheduler and run state."""

    def __init__(self, gmail_getter: Callable[[], GmailClient]):
        self._get_gmail = gmail_getter
        self._run_lock = asyncio.Lock()
        self._running = False
        self._label_id: Optional[str] = None
        self._classified_ids: Optional[set[str]] = None  # lazy-loaded
        self._last_run: Optional[dict] = None

    # ── State file ────────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        self._classified_ids = set()
        try:
            data = json.loads(config.ROUTINE_STATE_FILE.read_text())
            self._classified_ids = set(data.get("classified_ids", []))
            self._last_run = data.get("last_run")
        except (OSError, json.JSONDecodeError, TypeError):
            pass  # missing/corrupt file — start fresh; worst case is one re-pass

    def _save_state(self) -> None:
        ids = list(self._classified_ids or [])
        if len(ids) > _MAX_REMEMBERED_IDS:
            ids = ids[-_MAX_REMEMBERED_IDS:]
            self._classified_ids = set(ids)
        payload = json.dumps({"classified_ids": ids, "last_run": self._last_run})
        tmp = str(config.ROUTINE_STATE_FILE) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, config.ROUTINE_STATE_FILE)

    # ── Label ─────────────────────────────────────────────────────────────────

    def _ensure_label_id(self, gmail: GmailClient) -> str:
        """Find or create the Generic label; caches the ID."""
        if self._label_id:
            return self._label_id
        wanted = config.GENERIC_LABEL_NAME.lower()
        for label in gmail.get_labels():
            if label.get("name", "").lower() == wanted:
                self._label_id = label["id"]
                return self._label_id
        created = gmail.create_label(config.GENERIC_LABEL_NAME, bg_color="#999999")
        self._label_id = created["id"]
        return self._label_id

    # ── Classification ────────────────────────────────────────────────────────

    async def _classify_batch(self, client: ollama.AsyncClient, batch: list[dict]) -> Optional[list[bool]]:
        """Return one verdict per email, or None if the model output was
        unparsable twice (caller treats the whole batch as not-generic and
        leaves it out of the remembered set so it gets retried next run)."""
        lines = []
        for i, e in enumerate(batch, 1):
            snippet = " ".join((e.get("snippet") or "").split())[:_SNIPPET_LIMIT]
            lines.append(f'{i}. From: {e.get("sender", "")} | Subject: {e.get("subject", "")} | Snippet: {snippet}')
        prompt = _CLASSIFY_PROMPT.format(emails="\n".join(lines))

        for attempt in range(2):
            # No num_predict cap: thinking models (think=True) spend tokens on
            # reasoning BEFORE the answer — a cap can eat the whole budget and
            # return empty content.
            response = await client.chat(
                model=config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                **_think_kwargs(),
            )
            content = _strip_think(response.message.content or "")
            verdicts = self._parse_verdicts(content, len(batch))
            if verdicts is not None:
                return verdicts
            logger.warning("Unparsable classifier output (attempt %d): %.200s", attempt + 1, content)
        return None

    @staticmethod
    def _parse_verdicts(content: str, expected: int) -> Optional[list[bool]]:
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if not match:
            return None
        try:
            entries = json.loads(match.group())
        except json.JSONDecodeError:
            return None
        if not isinstance(entries, list):
            return None
        # Match by "n"; anything missing defaults to not-generic (conservative).
        verdicts = [False] * expected
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            n = entry.get("n")
            if isinstance(n, int) and 1 <= n <= expected:
                verdicts[n - 1] = bool(entry.get("generic", False))
        return verdicts

    # ── Run pipeline ──────────────────────────────────────────────────────────

    async def run_once(self, trigger: str) -> None:
        """One scan/classify/label pass. Never raises (except CancelledError);
        failures are recorded in last_run."""
        if self._run_lock.locked():
            return  # overlapping tick — the in-flight run covers it
        async with self._run_lock:
            self._running = True
            started = time.monotonic()
            scanned = labeled = skipped = 0
            errors: list[str] = []
            try:
                if self._classified_ids is None:
                    await asyncio.to_thread(self._load_state)

                gmail = await asyncio.to_thread(self._get_gmail)
                if not gmail.is_authenticated():
                    errors.append("Gmail is not connected")
                    return
                ok, hint = await asyncio.to_thread(ollama_status.is_available)
                if not ok:
                    errors.append(hint)
                    return

                query = (
                    f"in:inbox -label:{config.GENERIC_LABEL_NAME} "
                    f"newer_than:{config.ROUTINE_LOOKBACK_DAYS}d"
                )
                id_dicts = await asyncio.to_thread(
                    gmail.get_message_ids, config.ROUTINE_MAX_EMAILS_PER_RUN, query
                )
                fresh_ids = [d["id"] for d in id_dicts if d["id"] not in self._classified_ids]
                skipped = len(id_dicts) - len(fresh_ids)
                if not fresh_ids:
                    return

                emails: list[dict] = []
                for mid in fresh_ids:
                    try:
                        detail = await asyncio.to_thread(gmail.get_message_detail, mid)
                    except Exception:  # noqa: BLE001 — one bad message never aborts a run
                        logger.warning("Routine fetch failed for %s", mid, exc_info=True)
                        detail = None
                    if detail is not None:
                        emails.append(detail)
                    else:
                        errors.append(f"failed to fetch message {mid}")
                scanned = len(emails)

                label_id = await asyncio.to_thread(self._ensure_label_id, gmail)
                client = ollama.AsyncClient(host=config.OLLAMA_HOST)
                batch_size = max(1, config.ROUTINE_BATCH_SIZE)

                for i in range(0, len(emails), batch_size):
                    batch = emails[i : i + batch_size]
                    verdicts = await self._classify_batch(client, batch)
                    if verdicts is None:
                        errors.append(
                            f"batch {i // batch_size + 1}: unparsable model output (will retry next run)"
                        )
                        continue  # not remembered — retried on a future run
                    for email, is_generic in zip(batch, verdicts):
                        if is_generic:
                            try:
                                await asyncio.to_thread(gmail.apply_label, email["id"], label_id)
                                labeled += 1
                            except Exception:  # noqa: BLE001
                                # Label may have been deleted in Gmail; re-ensure once.
                                logger.warning("apply_label failed; re-ensuring label", exc_info=True)
                                self._label_id = None
                                try:
                                    label_id = await asyncio.to_thread(self._ensure_label_id, gmail)
                                    await asyncio.to_thread(gmail.apply_label, email["id"], label_id)
                                    labeled += 1
                                except Exception as e2:  # noqa: BLE001
                                    errors.append(f"label failed for {email['id']}: {e2}")
                        else:
                            self._classified_ids.add(email["id"])

                await asyncio.to_thread(self._save_state)

            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — recorded, never kills the scheduler
                logger.exception("Generic routine run failed")
                errors.append(str(e))
            finally:
                self._last_run = {
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "trigger": trigger,
                    "scanned": scanned,
                    "labeled": labeled,
                    "skipped": skipped,
                    "errors": errors,
                    "duration_seconds": round(time.monotonic() - started, 1),
                }
                try:
                    await asyncio.to_thread(self._save_state)
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to persist routine state", exc_info=True)
                self._running = False
                logger.info(
                    "Generic routine (%s): scanned=%d labeled=%d skipped=%d errors=%d",
                    trigger, scanned, labeled, skipped, len(errors),
                )

    async def scheduler_loop(self) -> None:
        """Run every ROUTINE_INTERVAL_MINUTES until cancelled (lifespan owns us)."""
        logger.info(
            "Generic routine scheduler started (every %d min)", config.ROUTINE_INTERVAL_MINUTES
        )
        await asyncio.sleep(60)  # let silent Gmail login / startup settle
        while True:
            await self.run_once(trigger="schedule")
            await asyncio.sleep(config.ROUTINE_INTERVAL_MINUTES * 60)

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        if self._classified_ids is None:
            self._load_state()  # cheap; surfaces last_run before the first run
        return {
            "enabled": config.ROUTINE_INTERVAL_MINUTES > 0,
            "interval_minutes": config.ROUTINE_INTERVAL_MINUTES,
            "running": self._running,
            "last_run": self._last_run,
        }
