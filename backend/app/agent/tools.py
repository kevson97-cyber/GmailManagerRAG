"""
tools.py — Agent tool registry: Ollama-format JSON schemas + sync executors.

Read-only tools are looked up in TOOL_EXECUTORS and run straight away via
`execute_read_tool()`. Destructive tools (DESTRUCTIVE_TOOLS) are split into a
`resolve` step (turns model args into a concrete, human-reviewable preview —
never mutates anything) and an `execute` step that only ever runs against the
FROZEN payload a resolve step already produced. `execute_destructive_tool()`
is the single choke point for that second step; engine.py must only call it
from the confirm-token resume path (see agent/engine.py), never from live
model output, so a destructive action is structurally unreachable without a
round-tripped user confirmation.

Executors never raise: validation errors and executor exceptions alike come
back as plain "Error: ..." strings, which the engine feeds to the model as a
tool result so it can self-correct.
"""
import json
import logging
from dataclasses import dataclass

from .. import categorizer
from ..gmail_client import GmailClient
from ..vector_store import EmailVectorStore

logger = logging.getLogger(__name__)

MAX_ITEMS = 30
SNIPPET_LEN = 150


@dataclass
class ToolContext:
    """Everything a tool executor needs — passed explicitly, never global state."""
    gmail: GmailClient
    vs: EmailVectorStore


# ── Category / label normalization (harvested verbatim from the old rag_engine) ──

CATEGORY_LABEL_MAP = {
    "social": "CATEGORY_SOCIAL", "promotions": "CATEGORY_PROMOTIONS",
    "promotion": "CATEGORY_PROMOTIONS", "promo": "CATEGORY_PROMOTIONS",
    "promos": "CATEGORY_PROMOTIONS", "updates": "CATEGORY_UPDATES",
    "update": "CATEGORY_UPDATES", "forums": "CATEGORY_FORUMS",
    "forum": "CATEGORY_FORUMS", "personal": "CATEGORY_PERSONAL",
    "spam": "SPAM", "starred": "STARRED", "important": "IMPORTANT",
    "sent": "SENT", "unread": "UNREAD",
}


def normalize_label(label: str) -> str:
    """
    Map a friendly category name (any case) to its Gmail label ID, e.g.
    'Promotions' -> 'CATEGORY_PROMOTIONS'. Raw IDs and user label names that
    aren't in the map (e.g. 'CATEGORY_SOCIAL', a custom label) pass through
    unchanged (original casing preserved).
    """
    cleaned = (label or "").strip()
    return CATEGORY_LABEL_MAP.get(cleaned.lower(), cleaned)


# ── Small shared helpers ──────────────────────────────────────────────────────

def _truncate_snippet(text: str, limit: int = SNIPPET_LEN) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _cap(items: list, limit: int = MAX_ITEMS) -> tuple[list, int]:
    """Return (first `limit` items, original total count)."""
    return items[:limit], len(items)


def _compact_email(e: dict) -> dict:
    return {
        "id": e.get("id", ""),
        "subject": e.get("subject", ""),
        "sender": e.get("sender", ""),
        "date": e.get("date", ""),
        "snippet": _truncate_snippet(e.get("snippet", "")),
    }


def _preview_item(e: dict) -> dict:
    return {
        "id": e.get("id", ""),
        "subject": e.get("subject", ""),
        "sender": e.get("sender", ""),
        "date": e.get("date", ""),
    }


def _find_label(label_query: str, ctx: ToolContext) -> dict | None:
    """Case-insensitive lookup of an existing Gmail label by name or raw ID/category alias."""
    normalized = normalize_label(label_query)
    query_lower = (label_query or "").strip().lower()
    for l in ctx.gmail.get_labels():
        if l.get("id", "").lower() == normalized.lower() or l.get("name", "").lower() == query_lower:
            return l
    return None


def _lookup_by_ids(email_ids: list[str], ctx: ToolContext) -> list[dict]:
    """Enrich explicit email IDs with indexed metadata where available (dedup, order preserved)."""
    wanted = list(dict.fromkeys(email_ids))
    by_id = {m["id"]: m for m in ctx.vs.get_all_metadata()}
    return [
        by_id.get(mid, {"id": mid, "subject": "", "sender": "", "date": "", "snippet": ""})
        for mid in wanted
    ]


def _resolve_selection(selection: dict, ctx: ToolContext) -> tuple[list[dict], str] | str:
    """
    Resolve a {sender?, label?, email_ids?} selection to concrete email dicts.
    Returns (matches, human description suffix), or an error string.
    """
    selection = selection or {}
    sender = (selection.get("sender") or "").strip()
    label = (selection.get("label") or "").strip()
    email_ids = selection.get("email_ids") or []

    if email_ids:
        return _lookup_by_ids(email_ids, ctx), f" (explicit selection of {len(email_ids)} email id(s))"
    if sender:
        return ctx.vs.get_by_sender(sender), f' from sender "{sender}"'
    if label:
        norm = normalize_label(label)
        return ctx.vs.get_by_label(norm), f' with label "{norm}"'
    return "Error: selection must include one of: sender, label, email_ids"


# ── JSON schemas (Ollama `tools=` format) ─────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": (
                "Semantic search over the indexed emails for messages relevant to a "
                "natural-language query. Use for fuzzy/topic-based lookups (e.g. "
                "'flight confirmations', 'invoices from last month')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language search query."},
                    "n_results": {"type": "integer", "description": "Max results to return (default 10)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_emails_by_sender",
            "description": (
                "List indexed emails from a specific sender (matches if the sender field "
                "contains this text, case-insensitive)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sender": {
                        "type": "string",
                        "description": "Sender name or email address (or a substring), e.g. 'chess.com'.",
                    },
                },
                "required": ["sender"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_emails_by_label",
            "description": (
                "List indexed emails carrying a specific Gmail label or category (e.g. "
                "'promotions', 'social', 'important', or a raw label ID like CATEGORY_SOCIAL)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Label name/category (e.g. 'promotions', 'spam', 'starred') or a raw Gmail label ID.",
                    },
                },
                "required": ["label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inbox_stats",
            "description": "Get aggregate stats for the indexed inbox: total indexed emails, unique sender count, and the top 5 senders.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_senders",
            "description": "List the most frequent senders in the indexed inbox, most emails first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Number of senders to return (default 20)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_emails",
            "description": (
                "Count indexed emails, optionally filtered by sender and/or label. Use this "
                "instead of search_emails when the user just wants a number."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sender": {"type": "string", "description": "Filter by sender substring (optional)."},
                    "label": {"type": "string", "description": "Filter by label/category (optional)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_labels",
            "description": "List all Gmail labels on the connected account (system and user-created).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_sender",
            "description": (
                "Get compact metadata (subject, date, snippet) for recent emails from a "
                "sender, for the assistant to summarize in its own words. Returns only real "
                "indexed data — never fabricate content beyond what this returns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sender": {"type": "string", "description": "Sender name or email address (or a substring)."},
                    "max_emails": {"type": "integer", "description": "Max emails to include (default 20)."},
                },
                "required": ["sender"],
            },
        },
    },
    # ── Destructive (confirmation required) ──────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "trash_emails",
            "description": (
                "Move matching emails to Gmail Trash (recoverable for 30 days). Calling this "
                "tool only PROPOSES the action — the system shows the user a confirmation "
                "with a preview before anything is deleted. Do not ask the user to confirm "
                "yourself; just call the tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "selection": {
                        "type": "object",
                        "description": "Which emails to trash. Provide exactly one of sender, label, or email_ids.",
                        "properties": {
                            "sender": {"type": "string", "description": "Trash all emails from this sender (substring match)."},
                            "label": {"type": "string", "description": "Trash all emails with this label/category."},
                            "email_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Trash these specific email IDs.",
                            },
                        },
                    },
                },
                "required": ["selection"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_label",
            "description": "Create a new Gmail label. Calling this tool only proposes the action — requires user confirmation before it's created.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the new label."},
                    "color": {
                        "type": "string",
                        "description": "Optional hex color (e.g. '#16a766'); snapped to Gmail's allowed palette.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_label",
            "description": (
                "Apply a Gmail label to matching emails, creating the label first if it "
                "doesn't exist. Calling this tool only proposes the action — requires user "
                "confirmation before anything changes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Label name to apply (created if it doesn't already exist)."},
                    "selection": {
                        "type": "object",
                        "description": "Which emails to label. Provide exactly one of sender, label, or email_ids.",
                        "properties": {
                            "sender": {"type": "string", "description": "Emails from this sender (substring match)."},
                            "label": {"type": "string", "description": "Emails with this existing label/category."},
                            "email_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "These specific email IDs.",
                            },
                        },
                    },
                },
                "required": ["label", "selection"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_filter",
            "description": (
                "Create a Gmail filter rule that automatically labels and/or archives future "
                "matching emails. Calling this tool only proposes the action — requires user "
                "confirmation before it's created. Provide at least one match criterion "
                "(from_sender, subject_contains, or query) and at least one action (add_label "
                "or skip_inbox)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_sender": {"type": "string", "description": "Match emails from this sender."},
                    "subject_contains": {"type": "string", "description": "Match emails whose subject contains this text."},
                    "query": {"type": "string", "description": "Raw Gmail search query to match on."},
                    "add_label": {"type": "string", "description": "Label to apply to matching emails (created if missing)."},
                    "skip_inbox": {"type": "boolean", "description": "Archive matching emails out of the inbox (default false)."},
                },
            },
        },
    },
]

DESTRUCTIVE_TOOLS: set[str] = {"trash_emails", "create_label", "apply_label", "create_filter"}

_SCHEMA_BY_NAME: dict[str, dict] = {s["function"]["name"]: s["function"] for s in TOOL_SCHEMAS}


# ── Arg validation ─────────────────────────────────────────────────────────────

def _check_type(value, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True  # unknown/unspecified schema type — don't block


def validate_args(tool_name: str, args: dict) -> str | None:
    """Validate args against the tool's JSON schema. Returns an error string, or None if OK."""
    schema = _SCHEMA_BY_NAME.get(tool_name)
    if schema is None:
        return f"Unknown tool '{tool_name}'."
    if not isinstance(args, dict):
        return f"Arguments for '{tool_name}' must be an object."

    params = schema.get("parameters", {})
    properties: dict = params.get("properties", {})
    required: list[str] = params.get("required", [])

    for key in required:
        if key not in args or args[key] is None:
            return f"Missing required argument '{key}' for tool '{tool_name}'."
        prop = properties.get(key, {})
        if prop.get("type") == "string" and isinstance(args[key], str) and not args[key].strip():
            return f"Missing required argument '{key}' for tool '{tool_name}'."

    for key, value in args.items():
        prop = properties.get(key)
        if prop is None:
            continue  # ignore unexpected extra args rather than hard-failing
        expected_type = prop.get("type")
        if expected_type and not _check_type(value, expected_type):
            return f"Argument '{key}' for tool '{tool_name}' must be of type {expected_type}."
        if expected_type == "object" and isinstance(value, dict):
            nested_props = prop.get("properties", {})
            for nested_key, nested_value in value.items():
                nested_prop = nested_props.get(nested_key)
                if nested_prop is None:
                    continue
                nested_type = nested_prop.get("type")
                if nested_type and not _check_type(nested_value, nested_type):
                    return (
                        f"Argument '{key}.{nested_key}' for tool '{tool_name}' "
                        f"must be of type {nested_type}."
                    )
    return None


# ── Read-only executors ────────────────────────────────────────────────────────

def _exec_search_emails(args: dict, ctx: ToolContext) -> dict:
    query = args["query"]
    n_results = max(1, min(int(args.get("n_results") or 10), MAX_ITEMS))
    results = ctx.vs.query(query, n_results)
    items, total = _cap(results)
    return {
        "results": [{**_compact_email(e), "score": e.get("score")} for e in items],
        "total_count": total,
    }


def _exec_get_emails_by_sender(args: dict, ctx: ToolContext) -> dict:
    sender = args["sender"]
    items, total = _cap(ctx.vs.get_by_sender(sender))
    return {"sender": sender, "results": [_compact_email(e) for e in items], "total_count": total}


def _exec_get_emails_by_label(args: dict, ctx: ToolContext) -> dict:
    label = normalize_label(args["label"])
    items, total = _cap(ctx.vs.get_by_label(label))
    return {"label": label, "results": [_compact_email(e) for e in items], "total_count": total}


def _exec_get_inbox_stats(args: dict, ctx: ToolContext) -> dict:
    stats = categorizer.get_inbox_stats(ctx.vs)
    return {
        "total_indexed": stats["total_indexed"],
        "unique_senders": stats["unique_senders"],
        "top_senders": [{"sender": s, "count": c} for s, c in stats["top_senders"]],
    }


def _exec_get_top_senders(args: dict, ctx: ToolContext) -> dict:
    n = max(1, min(int(args.get("n") or 20), MAX_ITEMS))
    senders = categorizer.get_top_senders(ctx.vs, n)
    return {"top_senders": [{"sender": s, "count": c} for s, c in senders], "total_count": len(senders)}


def _exec_count_emails(args: dict, ctx: ToolContext) -> dict:
    sender = (args.get("sender") or "").strip()
    label = (args.get("label") or "").strip()

    if not sender and not label:
        return {"count": ctx.vs.count()}
    if sender and not label:
        return {"count": len(ctx.vs.get_by_sender(sender)), "sender": sender}
    norm_label = normalize_label(label)
    if label and not sender:
        return {"count": len(ctx.vs.get_by_label(norm_label)), "label": norm_label}

    by_sender = ctx.vs.get_by_sender(sender)
    matched = [e for e in by_sender if norm_label.lower() in e.get("labels", "").lower()]
    return {"count": len(matched), "sender": sender, "label": norm_label}


def _exec_list_labels(args: dict, ctx: ToolContext) -> dict:
    items, total = _cap(ctx.gmail.get_labels())
    return {
        "labels": [{"id": l.get("id", ""), "name": l.get("name", ""), "type": l.get("type", "")} for l in items],
        "total_count": total,
    }


def _exec_summarize_sender(args: dict, ctx: ToolContext) -> dict:
    sender = args["sender"]
    max_emails = max(1, min(int(args.get("max_emails") or 20), MAX_ITEMS))
    results = ctx.vs.get_by_sender(sender)
    items = results[:max_emails]
    return {
        "sender": sender,
        "emails": [
            {
                "subject": e.get("subject", ""),
                "date": e.get("date", ""),
                "snippet": _truncate_snippet(e.get("snippet", "")),
            }
            for e in items
        ],
        "total_count": len(results),
    }


# ── Destructive: resolve (preview only, never mutates) ─────────────────────────

def _resolve_trash_emails(args: dict, ctx: ToolContext) -> dict | str:
    result = _resolve_selection(args.get("selection"), ctx)
    if isinstance(result, str):
        return result
    matches, desc = result
    ids = [m["id"] for m in matches]
    return {
        "description": f"Move {len(ids)} email(s) to Trash{desc}",
        "count": len(ids),
        "preview": [_preview_item(m) for m in matches[:10]],
        "resolved_ids": ids,
    }


def _resolve_create_label(args: dict, ctx: ToolContext) -> dict | str:
    name = (args.get("name") or "").strip()
    if not name:
        return "Error: name is required"
    color = (args.get("color") or "#16a766").strip()
    return {
        "description": f'Create Gmail label "{name}"',
        "count": 1,
        "preview": [],
        "resolved_args": {"name": name, "color": color},
    }


def _resolve_apply_label(args: dict, ctx: ToolContext) -> dict | str:
    label = (args.get("label") or "").strip()
    if not label:
        return "Error: label is required"
    result = _resolve_selection(args.get("selection"), ctx)
    if isinstance(result, str):
        return result
    matches, desc = result
    ids = [m["id"] for m in matches]

    existing = _find_label(label, ctx)
    label_note = f'existing label "{existing["name"]}"' if existing else f'new label "{label}" (will be created)'

    return {
        "description": f"Apply {label_note} to {len(ids)} email(s){desc}",
        "count": len(ids),
        "preview": [_preview_item(m) for m in matches[:10]],
        "resolved_ids": ids,
        "label_name": label,
        "existing_label_id": existing["id"] if existing else None,
    }


def _resolve_create_filter(args: dict, ctx: ToolContext) -> dict | str:
    from_sender = (args.get("from_sender") or "").strip()
    subject_contains = (args.get("subject_contains") or "").strip()
    query = (args.get("query") or "").strip()
    add_label = (args.get("add_label") or "").strip()
    skip_inbox = bool(args.get("skip_inbox", False))

    if not (from_sender or subject_contains or query):
        return "Error: at least one of from_sender, subject_contains, or query is required"

    criteria_desc = []
    if from_sender:
        criteria_desc.append(f'from "{from_sender}"')
    if subject_contains:
        criteria_desc.append(f'subject contains "{subject_contains}"')
    if query:
        criteria_desc.append(f'matching "{query}"')

    action_desc = []
    existing_label_id = None
    if add_label:
        existing = _find_label(add_label, ctx)
        if existing:
            action_desc.append(f'add label "{existing["name"]}"')
            existing_label_id = existing["id"]
        else:
            action_desc.append(f'add new label "{add_label}" (will be created)')
    if skip_inbox:
        action_desc.append("skip the inbox")

    if not action_desc:
        return "Error: create_filter needs at least one action (add_label or skip_inbox)"

    description = f"Create a filter for emails {', '.join(criteria_desc)}: {', '.join(action_desc)}"

    return {
        "description": description,
        "count": 1,
        "preview": [],
        "resolved_args": {
            "from_sender": from_sender,
            "subject_contains": subject_contains,
            "query": query,
            "add_label": add_label,
            "skip_inbox": skip_inbox,
            "existing_label_id": existing_label_id,
        },
    }


RESOLVERS: dict = {
    "trash_emails": _resolve_trash_emails,
    "create_label": _resolve_create_label,
    "apply_label": _resolve_apply_label,
    "create_filter": _resolve_create_filter,
}


# ── Destructive: execute (only ever runs against a frozen resolved payload) ────

def _exec_trash_emails_confirmed(resolved: dict, ctx: ToolContext) -> str:
    ids = resolved.get("resolved_ids", [])
    if not ids:
        return "No emails matched — nothing to trash."
    trashed, errors = ctx.gmail.trash_emails(ids)
    if trashed:
        ctx.vs.remove_emails(trashed)
    return f"Moved {len(trashed)} emails to Trash ({len(errors)} errors)."


def _exec_create_label_confirmed(resolved: dict, ctx: ToolContext) -> str:
    ra = resolved.get("resolved_args", {})
    name = ra.get("name", "")
    color = ra.get("color", "#16a766")
    label = ctx.gmail.create_label(name, bg_color=color)
    return f'Created label "{label.get("name", name)}" (id {label.get("id", "?")}).'


def _exec_apply_label_confirmed(resolved: dict, ctx: ToolContext) -> str:
    ids = resolved.get("resolved_ids", [])
    if not ids:
        return "No emails matched — nothing to label."
    label_name = resolved.get("label_name", "")
    label_id = resolved.get("existing_label_id")
    if not label_id:
        existing = _find_label(label_name, ctx)
        label_id = existing["id"] if existing else ctx.gmail.create_label(label_name).get("id", "")

    applied = 0
    errors = 0
    for mid in ids:
        try:
            ctx.gmail.apply_label(mid, label_id)
            applied += 1
        except Exception:
            logger.warning("apply_label failed for message %s", mid, exc_info=True)
            errors += 1
    return f'Applied label "{label_name}" to {applied} email(s) ({errors} errors).'


def _exec_create_filter_confirmed(resolved: dict, ctx: ToolContext) -> str:
    ra = resolved.get("resolved_args", {})
    criteria: dict = {}
    if ra.get("from_sender"):
        criteria["from"] = ra["from_sender"]
    if ra.get("subject_contains"):
        criteria["subject"] = ra["subject_contains"]
    if ra.get("query"):
        criteria["query"] = ra["query"]

    action: dict = {}
    add_label = ra.get("add_label")
    if add_label:
        label_id = ra.get("existing_label_id")
        if not label_id:
            existing = _find_label(add_label, ctx)
            label_id = existing["id"] if existing else ctx.gmail.create_label(add_label).get("id", "")
        action["addLabelIds"] = [label_id]
    if ra.get("skip_inbox"):
        action["removeLabelIds"] = action.get("removeLabelIds", []) + ["INBOX"]

    if not criteria or not action:
        return "Error: filter criteria/action incomplete."

    result = ctx.gmail.create_filter(criteria, action)
    return f"Created Gmail filter (id {result.get('id', '?')})."


# TOOL_EXECUTORS holds every tool's real implementation, keyed by name.
# Read-only entries take (raw validated args, ctx). Destructive entries take
# (frozen `resolved` payload from RESOLVERS, ctx) — see execute_destructive_tool.
TOOL_EXECUTORS: dict = {
    "search_emails": _exec_search_emails,
    "get_emails_by_sender": _exec_get_emails_by_sender,
    "get_emails_by_label": _exec_get_emails_by_label,
    "get_inbox_stats": _exec_get_inbox_stats,
    "get_top_senders": _exec_get_top_senders,
    "count_emails": _exec_count_emails,
    "list_labels": _exec_list_labels,
    "summarize_sender": _exec_summarize_sender,
    "trash_emails": _exec_trash_emails_confirmed,
    "create_label": _exec_create_label_confirmed,
    "apply_label": _exec_apply_label_confirmed,
    "create_filter": _exec_create_filter_confirmed,
}


# ── Dispatchers (the only entry points engine.py should call) ──────────────────

def execute_read_tool(name: str, args: dict, ctx: ToolContext) -> dict | str:
    """Validate + run a read-only tool. Never raises — always returns dict|error-string."""
    if name in DESTRUCTIVE_TOOLS:
        return f"Error: '{name}' requires user confirmation and cannot be executed directly."
    error = validate_args(name, args)
    if error:
        return f"Error: {error}"
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return f"Error: unknown tool '{name}'."
    try:
        return executor(args, ctx)
    except Exception as e:  # noqa: BLE001 — fed back to the model as a tool result
        logger.exception("Tool '%s' failed", name)
        return f"Error: {e}"


def resolve_destructive_tool(name: str, args: dict, ctx: ToolContext) -> dict | str:
    """Validate + resolve a destructive tool to a preview. Never mutates anything."""
    if name not in DESTRUCTIVE_TOOLS:
        return f"Error: '{name}' is not a destructive tool."
    error = validate_args(name, args)
    if error:
        return f"Error: {error}"
    resolver = RESOLVERS.get(name)
    if resolver is None:
        return f"Error: no resolver registered for '{name}'."
    try:
        return resolver(args, ctx)
    except Exception as e:  # noqa: BLE001
        logger.exception("Resolve for '%s' failed", name)
        return f"Error: {e}"


def execute_destructive_tool(name: str, resolved: dict, ctx: ToolContext) -> str:
    """
    Execute a destructive tool against the FROZEN payload a prior
    resolve_destructive_tool() call produced. This is the only place a
    destructive TOOL_EXECUTORS entry is invoked — callers must come from
    engine.py's confirm-token resume path (see PendingAction), never from
    live model output, so nothing destructive can run without a completed
    confirm round-trip.
    """
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return f"Error: unknown tool '{name}'."
    try:
        result = executor(resolved, ctx)
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as e:  # noqa: BLE001
        logger.exception("Execution for '%s' failed", name)
        return f"Error: {e}"
