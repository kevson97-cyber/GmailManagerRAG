"""
ollama_status.py — Check whether Ollama is reachable and the configured
model is pulled. Ported from the old rag_engine's connectivity check;
messages are written to be actionable in the UI.
"""
import ollama

from . import config

# Model families whose Ollama build routes reasoning into a separate
# message.thinking field when think=True is passed — for other families
# (e.g. llama3.2) the param is either ignored or rejected outright, so it
# must be omitted entirely rather than passed as False.
_THINKING_MODEL_PREFIXES = ("qwen3", "deepseek-r1")


def think_kwargs() -> dict:
    """kwargs to pass to ollama.chat()/AsyncClient.chat() for the configured
    model: {"think": True} for thinking-capable families, {} otherwise."""
    if config.OLLAMA_MODEL.lower().startswith(_THINKING_MODEL_PREFIXES):
        return {"think": True}
    return {}


def is_available() -> tuple[bool, str]:
    """
    Return (ok, message).

    ok=True  → message is empty (or informational).
    ok=False → message tells the user exactly what to run to fix it.
    """
    try:
        client = ollama.Client(host=config.OLLAMA_HOST)
        response = client.list()
    except Exception:
        return False, "Ollama not running — start it with: ollama serve"

    # ollama-py has changed the shape of list() across versions: older
    # releases return a plain dict {"models": [{"name": ...}]}; newer
    # releases return an object with a `.models` attribute of model objects
    # that expose `.model` (and sometimes `.name`).
    if isinstance(response, dict):
        raw_models = response.get("models", [])
    else:
        raw_models = getattr(response, "models", [])

    names: list[str] = []
    for m in raw_models:
        if isinstance(m, dict):
            name = m.get("name") or m.get("model") or ""
        else:
            name = getattr(m, "model", None) or getattr(m, "name", None) or ""
        if name:
            names.append(name)

    wanted_prefix = config.OLLAMA_MODEL.split(":")[0]
    if any(wanted_prefix in name for name in names):
        return True, ""

    return (
        False,
        f"Model '{config.OLLAMA_MODEL}' not found. Run: ollama pull {config.OLLAMA_MODEL}",
    )
