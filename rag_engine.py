"""
rag_engine.py — RAG layer: retrieve relevant emails from ChromaDB, then
                answer questions / suggest categories using a local Ollama model.
"""
import json
import re
from typing import Optional

import ollama as _ollama

from config import OLLAMA_HOST, OLLAMA_MODEL
from vector_store import EmailVectorStore


def _ollama_client():
    """Return an Ollama client pointed at the configured host."""
    return _ollama.Client(host=OLLAMA_HOST)


def _chat(messages: list[dict], max_tokens: int = 2048) -> str:
    """
    Send a chat request to Ollama and return the response text.
    Raises a clear error if Ollama is not running.
    """
    try:
        client = _ollama_client()
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            options={"num_predict": max_tokens},
        )
        # Support both dict-style and object-style responses
        if isinstance(response, dict):
            return response["message"]["content"]
        return response.message.content
    except Exception as e:
        err = str(e).lower()
        if "connection" in err or "refused" in err or "connect" in err:
            raise ConnectionError(
                f"Cannot reach Ollama at {OLLAMA_HOST}.\n"
                "Make sure Ollama is running — open a terminal and run:  ollama serve"
            ) from e
        if "not found" in err or "unknown model" in err:
            raise ValueError(
                f"Model '{OLLAMA_MODEL}' is not installed in Ollama.\n"
                f"Install it with:  ollama pull {OLLAMA_MODEL}"
            ) from e
        raise


class RAGEngine:
    """Retrieval-Augmented Generation over the indexed email corpus."""

    def __init__(self, vector_store: EmailVectorStore):
        self.vs = vector_store

    def is_available(self) -> tuple[bool, str]:
        """
        Check whether Ollama is running and the model is available.
        Returns (ok: bool, message: str).
        """
        try:
            client = _ollama_client()
            models = client.list()
            model_names = []
            if isinstance(models, dict) and "models" in models:
                model_names = [m.get("name", m.get("model", "")) for m in models["models"]]
            elif hasattr(models, "models"):
                model_names = [
                    getattr(m, "name", None) or getattr(m, "model", "")
                    for m in models.models
                ]
            # Accept prefix match (e.g. "llama3.2" matches "llama3.2:latest")
            if not any(OLLAMA_MODEL.split(":")[0] in n for n in model_names):
                return False, (
                    f"Model '{OLLAMA_MODEL}' not found.\n"
                    f"Run: ollama pull {OLLAMA_MODEL}"
                )
            return True, f"Ollama ready  ·  model: {OLLAMA_MODEL}"
        except Exception as e:
            return False, f"Ollama not running — start it with: ollama serve\n({e})"

    # ── Chat / Q&A ────────────────────────────────────────────────────────────

    def chat(self, question: str, history: Optional[list[dict]] = None) -> str:
        """
        Answer a question about the user's inbox.

        1. Retrieves the most semantically relevant emails from ChromaDB.
        2. Injects them as context into the system prompt.
        3. Passes conversation history for multi-turn support.
        """
        relevant = self.vs.query(question, n_results=8)

        if relevant:
            context_lines = ["Here are the most relevant emails from the user's inbox:\n"]
            for i, e in enumerate(relevant, 1):
                context_lines.append(
                    f"[Email {i}]\n"
                    f"Subject : {e['subject']}\n"
                    f"From    : {e['sender']}\n"
                    f"Date    : {e['date']}\n"
                    f"Preview : {e['snippet']}\n"
                    f"(Relevance score: {e['score']})\n"
                )
            context = "\n".join(context_lines)
        else:
            context = "No emails have been indexed yet."

        system_content = (
            "You are an intelligent Gmail assistant. "
            "You have access to a semantic index of the user's inbox. "
            "Answer questions accurately, reference specific emails where helpful, "
            "and be concise and actionable.\n\n"
            f"INBOX CONTEXT:\n{context}"
        )

        messages: list[dict] = [{"role": "system", "content": system_content}]
        if history:
            for turn in history[-6:]:
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": question})

        return _chat(messages, max_tokens=2048)

    # ── Category Suggestions ─────────────────────────────────────────────────

    def suggest_categories(self, sample_size: int = 300) -> list[dict]:
        """
        Ask the model to analyse a sample of the inbox and propose 5-8
        meaningful label categories with filter criteria.
        """
        all_meta = self.vs.get_all_metadata()
        if not all_meta:
            return []

        sample = all_meta[:sample_size]
        summary = "\n".join(
            f"- From: {m.get('sender', '')} | Subject: {m.get('subject', '')}"
            for m in sample
        )

        prompt = f"""Analyse the following {len(sample)} emails from a Gmail inbox and suggest 5-8 meaningful categories/labels for organising them.

EMAILS:
{summary}

For each category output a JSON object with:
- "name"             : short label name (2-3 words, title-case)
- "description"      : one-sentence description
- "filter_criteria"  : object with optional keys "from_contains" (list of strings), "subject_contains" (list of strings)
- "color"            : a hex color code that suits the category

Respond with ONLY a valid JSON array — no markdown, no prose."""

        messages = [{"role": "user", "content": prompt}]
        text = _chat(messages, max_tokens=2500)
        return self._parse_json_list(text)

    # ── Filter Rule Generation ─────────────────────────────────────────────────

    def generate_filter_rules(self, category: dict, sample_emails: list[dict]) -> dict:
        """
        Given a category and sample matching emails, produce a concrete
        Gmail filter object.
        """
        examples = "\n".join(
            f"- From: {e.get('sender', '')} | Subject: {e.get('subject', '')}"
            for e in sample_emails[:20]
        )

        prompt = f"""Generate a Gmail filter rule for this email category.

Category    : {category['name']}
Description : {category['description']}

Sample matching emails:
{examples}

Return ONLY a JSON object in this exact format:
{{
  "criteria": {{
    "from": "address1@example.com OR @domain.com",
    "subject": "keyword1 OR keyword2"
  }},
  "action": {{
    "addLabelIds": ["LABEL_PLACEHOLDER"],
    "removeLabelIds": ["INBOX"]
  }}
}}

Rules:
- "from" and "subject" are Gmail search query strings (OR-separated values work).
- Include "removeLabelIds": ["INBOX"] only if these emails should skip the inbox.
- Do NOT include empty strings.
- Respond with ONLY the JSON object."""

        messages = [{"role": "user", "content": prompt}]
        text = _chat(messages, max_tokens=600)
        return self._parse_json_object(text)

    # ── Deletion helpers ──────────────────────────────────────────────────────

    # Keywords that signal the user wants to delete/trash emails
    _DELETE_KEYWORDS = {
        "delete", "trash", "remove", "get rid of", "clean up",
        "purge", "clear out", "throw away", "discard", "wipe",
    }

    # Map common user-facing category names → Gmail label IDs
    _CATEGORY_LABEL_MAP = {
        "social":       "CATEGORY_SOCIAL",
        "promotions":   "CATEGORY_PROMOTIONS",
        "promotion":    "CATEGORY_PROMOTIONS",
        "promo":        "CATEGORY_PROMOTIONS",
        "promos":       "CATEGORY_PROMOTIONS",
        "updates":      "CATEGORY_UPDATES",
        "update":       "CATEGORY_UPDATES",
        "forums":       "CATEGORY_FORUMS",
        "forum":        "CATEGORY_FORUMS",
        "personal":     "CATEGORY_PERSONAL",
        "spam":         "SPAM",
        "starred":      "STARRED",
        "important":    "IMPORTANT",
        "sent":         "SENT",
        "unread":       "UNREAD",
    }

    @classmethod
    def is_delete_intent(cls, text: str) -> bool:
        """Return True if the user's message is asking to delete emails."""
        lower = text.lower()
        return any(kw in lower for kw in cls._DELETE_KEYWORDS)

    @classmethod
    def _detect_label(cls, query: str) -> Optional[str]:
        """
        Return a Gmail label ID if the query references a known category name,
        otherwise return None.
        e.g. 'delete social emails' → 'CATEGORY_SOCIAL'
        """
        lower = query.lower()
        for keyword, label_id in cls._CATEGORY_LABEL_MAP.items():
            if re.search(rf"\b{re.escape(keyword)}\b", lower):
                return label_id
        return None

    @staticmethod
    def _detect_sender(query: str) -> Optional[str]:
        """
        Extract a sender domain or address from the query.
        e.g. 'delete emails from chess.com' → 'chess.com'
             'remove emails from noreply@amazon.com' → 'noreply@amazon.com'
        Returns the raw sender string or None.
        """
        m = re.search(
            r"\bfrom\s+([\w.\-@]+\.[a-z]{2,})",
            query,
            flags=re.IGNORECASE,
        )
        return m.group(1).lower() if m else None

    def find_emails_for_deletion(self, query: str, n_results: int = 1500) -> list[dict]:
        """
        Find candidate emails for deletion.

        Priority order:
        1. Category label match (Social, Promotions, …) → metadata filter
        2. Sender / domain match ('from chess.com') → metadata filter
        3. Semantic similarity search (fallback)
        """
        # 1. Label-based
        label = self._detect_label(query)
        if label:
            return self.vs.get_by_label(label)

        # 2. Sender/domain-based
        sender_term = self._detect_sender(query)
        if sender_term:
            return self.vs.get_by_sender(sender_term)

        # 3. Semantic fallback
        clean = re.sub(
            r"\b(delete|trash|remove|get rid of|clean(?:\s+up)?|purge|"
            r"clear(?:\s+out)?|throw\s+away|discard|wipe)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip() or query
        return self.vs.query(clean, n_results=n_results)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json_list(text: str) -> list:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return []

    @staticmethod
    def _parse_json_object(text: str) -> dict:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}
