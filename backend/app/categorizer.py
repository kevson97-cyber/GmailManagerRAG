"""
email_categorizer.py — Higher-level helpers: stats, pattern detection,
                        and AI-enriched category suggestions.
"""
from collections import Counter

from vector_store import EmailVectorStore
from rag_engine import RAGEngine


class EmailCategorizer:
    """Orchestrates category suggestions and inbox analytics."""

    def __init__(self, vector_store: EmailVectorStore, rag_engine: RAGEngine):
        self.vs = vector_store
        self.rag = rag_engine

    # ── Analytics ─────────────────────────────────────────────────────────────

    def get_inbox_stats(self) -> dict:
        """Return aggregate stats for the indexed corpus."""
        metadata = self.vs.get_all_metadata()
        total = len(metadata)
        senders = Counter(m.get("sender", "") for m in metadata)

        return {
            "total_indexed": total,
            "unique_senders": len(senders),
            "top_senders": senders.most_common(5),
        }

    def get_top_senders(self, n: int = 20) -> list[tuple[str, int]]:
        metadata = self.vs.get_all_metadata()
        return Counter(m.get("sender", "") for m in metadata).most_common(n)

    # ── Category Analysis ─────────────────────────────────────────────────────

    def find_emails_for_category(self, category: dict, n: int = 15) -> list[dict]:
        """Semantic search for emails that likely belong to this category."""
        query = f"{category['name']} {category['description']}"
        return self.vs.query(query, n_results=n)

    def suggest_and_analyze(self) -> list[dict]:
        """
        Full pipeline:
        1. Ask Claude to suggest categories from indexed email metadata.
        2. Retrieve sample matching emails for each category.
        Returns enriched list of category dicts.
        """
        categories = self.rag.suggest_categories()
        enriched = []
        for cat in categories:
            matching = self.find_emails_for_category(cat)
            enriched.append({**cat, "matching_emails": matching})
        return enriched
