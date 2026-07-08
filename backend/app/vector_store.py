"""
vector_store.py — ChromaDB-backed persistent vector store for Gmail emails.

Uses sentence-transformers (all-MiniLM-L6-v2) for local, free embeddings.
"""
import json
from typing import Callable, Optional

import chromadb
from sentence_transformers import SentenceTransformer

from config import CHROMA_DIR, CHROMA_COLLECTION_NAME, EMBEDDING_MODEL


class EmailVectorStore:
    """Persistent ChromaDB collection of embedded Gmail messages."""

    def __init__(self):
        self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self._collection = self._client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._model: Optional[SentenceTransformer] = None

    # ── Embedding ─────────────────────────────────────────────────────────────

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the embedding model (downloads once, then cached)."""
        if self._model is None:
            self._model = SentenceTransformer(EMBEDDING_MODEL)
        return self._model

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, show_progress_bar=False).tolist()

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_emails(
        self,
        emails: list[dict],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """
        Embed and store emails.  Skips duplicates by message ID.
        Returns the count of newly added emails.
        """
        existing_ids: set[str] = set(self._collection.get(include=[])["ids"])
        new_emails = [e for e in emails if e["id"] not in existing_ids]

        if not new_emails:
            return 0

        batch_size = 50
        added = 0

        for i in range(0, len(new_emails), batch_size):
            batch = new_emails[i : i + batch_size]

            # Build rich text for embedding: subject + sender + date + body snippet
            texts = [
                (
                    f"Subject: {e['subject']}\n"
                    f"From: {e['sender']}\n"
                    f"Date: {e['date']}\n\n"
                    f"{e.get('snippet', '')}\n\n"
                    f"{e.get('body', '')[:500]}"
                )
                for e in batch
            ]

            embeddings = self._embed(texts)

            self._collection.add(
                ids=[e["id"] for e in batch],
                embeddings=embeddings,
                documents=texts,
                metadatas=[
                    {
                        "subject": e["subject"][:200],
                        "sender": e["sender"][:200],
                        "recipient": e.get("recipient", "")[:200],
                        "date": e["date"][:100],
                        "snippet": e.get("snippet", "")[:500],
                        "labels": json.dumps(e.get("labels", [])),
                    }
                    for e in batch
                ],
            )

            added += len(batch)
            if progress_callback:
                progress_callback(added, len(new_emails))

        return added

    # ── Read ──────────────────────────────────────────────────────────────────

    def query(self, query_text: str, n_results: int = 10) -> list[dict]:
        """
        Semantic search: return the n most relevant emails for query_text.
        Each result dict contains: id, subject, sender, date, snippet, score.
        """
        total = self.count()
        if total == 0:
            return []

        n = min(n_results, total)
        embedding = self._embed([query_text])

        result = self._collection.query(
            query_embeddings=embedding,
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )

        emails = []
        for idx, doc_id in enumerate(result["ids"][0]):
            meta = result["metadatas"][0][idx]
            emails.append(
                {
                    "id": doc_id,
                    "document": result["documents"][0][idx],
                    "subject": meta.get("subject", ""),
                    "sender": meta.get("sender", ""),
                    "date": meta.get("date", ""),
                    "snippet": meta.get("snippet", ""),
                    # cosine distance → similarity score (0-1, higher = more relevant)
                    "score": round(1 - result["distances"][0][idx], 4),
                }
            )

        return emails

    def get_by_sender(self, sender_term: str) -> list[dict]:
        """
        Return all emails where the sender field contains sender_term (case-insensitive).
        e.g. 'chess.com' matches 'noreply@chess.com', 'info@chess.com', etc.
        """
        if self.count() == 0:
            return []
        result = self._collection.get(include=["metadatas"])
        term = sender_term.lower()
        emails = []
        for doc_id, meta in zip(result["ids"], result["metadatas"]):
            if term in meta.get("sender", "").lower():
                emails.append({
                    "id": doc_id,
                    "subject": meta.get("subject", ""),
                    "sender": meta.get("sender", ""),
                    "date": meta.get("date", ""),
                    "snippet": meta.get("snippet", ""),
                    "labels": meta.get("labels", "[]"),
                    "score": 1.0,
                })
        return emails

    def get_by_label(self, label: str) -> list[dict]:
        """
        Return all emails whose stored labels JSON contains the given label string.
        label should be a Gmail label ID, e.g. 'CATEGORY_SOCIAL', 'CATEGORY_PROMOTIONS'.
        Does a full scan of stored metadata and matches by substring — guaranteed to
        work across all ChromaDB versions.
        Returns dicts with: id, subject, sender, date, snippet, labels, score=1.0.
        """
        if self.count() == 0:
            return []

        # Full scan — labels field is a JSON string like '["CATEGORY_SOCIAL","INBOX"]'
        result = self._collection.get(include=["metadatas"])
        label_lower = label.lower()

        emails = []
        for doc_id, meta in zip(result["ids"], result["metadatas"]):
            if label_lower in meta.get("labels", "").lower():
                emails.append(
                    {
                        "id": doc_id,
                        "subject": meta.get("subject", ""),
                        "sender": meta.get("sender", ""),
                        "date": meta.get("date", ""),
                        "snippet": meta.get("snippet", ""),
                        "labels": meta.get("labels", "[]"),
                        "score": 1.0,
                    }
                )
        return emails

    def get_all_metadata(self) -> list[dict]:
        """Return metadata dicts for every stored email (no embeddings)."""
        result = self._collection.get(include=["metadatas"])
        return [
            {"id": doc_id, **meta}
            for doc_id, meta in zip(result["ids"], result["metadatas"])
        ]

    def count(self) -> int:
        return self._collection.count()

    # ── Maintenance ───────────────────────────────────────────────────────────

    def remove_emails(self, email_ids: list[str]) -> None:
        """Remove specific emails from the index by their message IDs."""
        if email_ids:
            self._collection.delete(ids=email_ids)

    def clear(self):
        """Delete and recreate the collection (wipes all indexed emails)."""
        self._client.delete_collection(CHROMA_COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
