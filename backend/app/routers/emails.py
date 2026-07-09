"""
routers/emails.py — Read-only email browser (search/filter/sort/paginate over
the indexed corpus), index clearing, and aggregate stats.

Chroma has no native sender/label filter or field sort, so this does a full
metadata scan + in-Python filter/sort — fine up to a few thousand emails (see
plan risk notes); a future phase could move this to a real DB if it matters.
"""
import asyncio
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status

from .. import categorizer, deps
from ..auth import require_token
from ..models import EmailItem, EmailListResponse, StatsResponse

router = APIRouter(tags=["emails"], dependencies=[Depends(require_token)])

MAX_LIMIT = 200
SORT_FIELDS = ("date", "sender", "subject")
TOP_SENDERS_COUNT = 10


def _parse_date(date_str: str) -> datetime | None:
    """
    Best-effort parse of the `date` metadata field, or None on failure.

    gmail_client.py normally stores an ISO-8601 string; fall back to raw
    RFC2822 header parsing. Aware datetimes are normalized to naive UTC so
    they're comparable against each other regardless of source format.
    """
    if date_str:
        for parser in (datetime.fromisoformat, parsedate_to_datetime):
            try:
                dt = parser(date_str)
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except (ValueError, TypeError):
                continue
    return None


def _sort_items(items: list[dict], sort: str, order: str) -> list[dict]:
    """
    Sort by date/sender/subject, ascending or descending.

    Date sort is special-cased: items whose date fails to parse are always
    appended at the end (in original order) regardless of `order`, rather
    than naively reversing a (rank, value) tuple — which would otherwise
    flip unparseable items to the *front* under desc order.
    """
    reverse = order == "desc"

    if sort != "date":
        key_fn = (lambda i: i.get("sender", "").lower()) if sort == "sender" \
            else (lambda i: i.get("subject", "").lower())
        return sorted(items, key=key_fn, reverse=reverse)

    dated: list[tuple[datetime, dict]] = []
    undated: list[dict] = []
    for item in items:
        dt = _parse_date(item.get("date", ""))
        (dated.append((dt, item)) if dt is not None else undated.append(item))

    dated.sort(key=lambda pair: pair[0], reverse=reverse)
    return [item for _, item in dated] + undated


def _list_emails(
    search: str, label: str, sender: str, sort: str, order: str, offset: int, limit: int
) -> tuple[int, list[dict]]:
    """Blocking filter/sort/paginate over vs.get_all_metadata(). Run via asyncio.to_thread."""
    vs = deps.get_vector_store()
    rows = vs.get_all_metadata()

    items = []
    for row in rows:
        labels_raw = row.get("labels", "[]")
        try:
            labels = json.loads(labels_raw) if isinstance(labels_raw, str) else list(labels_raw)
        except (json.JSONDecodeError, TypeError):
            labels = []
        items.append({**row, "labels": labels})

    search_l = search.lower().strip()
    label_l = label.lower().strip()
    sender_l = sender.lower().strip()

    def matches(item: dict) -> bool:
        if search_l and not (
            search_l in item.get("subject", "").lower()
            or search_l in item.get("sender", "").lower()
            or search_l in item.get("snippet", "").lower()
        ):
            return False
        if label_l and not any(label_l in lbl.lower() for lbl in item.get("labels", [])):
            return False
        if sender_l and sender_l not in item.get("sender", "").lower():
            return False
        return True

    filtered = [item for item in items if matches(item)]
    filtered = _sort_items(filtered, sort, order)

    total = len(filtered)
    page = filtered[offset : offset + limit]
    return total, page


@router.get("/api/emails", response_model=EmailListResponse)
async def list_emails(
    search: str = "",
    label: str = "",
    sender: str = "",
    sort: str = "date",
    order: str = "desc",
    offset: int = 0,
    limit: int = 50,
) -> EmailListResponse:
    """Filtered/sorted/paginated view over the indexed corpus."""
    if sort not in SORT_FIELDS:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"sort must be one of: {', '.join(SORT_FIELDS)}",
        )
    if order not in ("asc", "desc"):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="order must be one of: asc, desc"
        )

    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)

    total, page = await asyncio.to_thread(
        _list_emails, search, label, sender, sort, order, offset, limit
    )

    return EmailListResponse(
        total=total,
        items=[
            EmailItem(
                id=row.get("id", ""),
                subject=row.get("subject", ""),
                sender=row.get("sender", ""),
                recipient=row.get("recipient", ""),
                date=row.get("date", ""),
                snippet=row.get("snippet", ""),
                labels=row.get("labels", []),
            )
            for row in page
        ],
    )


@router.delete("/api/emails/index")
async def clear_index() -> dict:
    """Wipe the Chroma collection. Refused while a sync job is running."""
    manager = deps.get_sync_manager()
    if manager.running:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Cannot clear the index while a sync is running",
        )

    vs = await asyncio.to_thread(deps.get_vector_store)
    await asyncio.to_thread(vs.clear)
    return {"cleared": True}


@router.get("/api/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    """Aggregate stats over the indexed corpus for the Sync page."""

    def _compute() -> dict:
        vs = deps.get_vector_store()
        inbox_stats = categorizer.get_inbox_stats(vs)
        top_senders = categorizer.get_top_senders(vs, TOP_SENDERS_COUNT)
        return {
            "total_indexed": inbox_stats["total_indexed"],
            "unique_senders": inbox_stats["unique_senders"],
            "top_senders": top_senders,
        }

    stats = await asyncio.to_thread(_compute)
    return StatsResponse(**stats)
