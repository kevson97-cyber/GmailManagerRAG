"""
categorizer.py — Inbox analytics helpers (stats, top senders).

Category suggestion / AI enrichment lived here in the Streamlit-era app; the
new architecture folds that into the agent's `get_inbox_stats` /
`get_top_senders` tools (see app/agent/tools.py, Phase 3), so this module is
trimmed to pure aggregation over the vector store's metadata.
"""
from collections import Counter

from .vector_store import EmailVectorStore


def get_inbox_stats(vs: EmailVectorStore) -> dict:
    """Return aggregate stats for the indexed corpus."""
    metadata = vs.get_all_metadata()
    total = len(metadata)
    senders = Counter(m.get("sender", "") for m in metadata)

    return {
        "total_indexed": total,
        "unique_senders": len(senders),
        "top_senders": senders.most_common(5),
    }


def get_top_senders(vs: EmailVectorStore, n: int = 20) -> list[tuple[str, int]]:
    """Return the n most frequent senders in the indexed corpus."""
    metadata = vs.get_all_metadata()
    return Counter(m.get("sender", "") for m in metadata).most_common(n)
