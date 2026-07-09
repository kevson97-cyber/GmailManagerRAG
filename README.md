# GmailManagerRAG

A local-first Gmail assistant. Your email index, Gmail credentials, and AI model all stay on **your PC** — nothing is sent to a paid API. A mobile-friendly web UI (deployable to Vercel) connects back to your PC through a free Cloudflare Tunnel.

```
┌─────────────┐  HTTPS   ┌───────────────────┐        ┌──────────────────────────┐
│ Phone /     │ ───────► │ Cloudflare Tunnel │ ─────► │ Your PC                  │
│ browser     │          │ (free)            │        │  FastAPI backend :8000   │
│ (Next.js UI │          └───────────────────┘        │  ├─ Gmail API (OAuth)    │
│  on Vercel) │                                       │  ├─ ChromaDB index       │
└─────────────┘                                       │  └─ Ollama (qwen3:4b)    │
                                                      └──────────────────────────┘
```

**Two pages:**

- **Sync & Index** — connect Gmail, sync emails into a local semantic index (ChromaDB + sentence-transformers), and browse every indexed email by subject, sender, recipient, date, labels, and snippet with search/filter/sort.
- **Assistant** — chat (typed or voice) with a local Ollama agent that uses **real tool calling**: search your emails semantically, count/rank senders, summarize, create labels and filters, and trash emails — every destructive action shows a preview and requires your explicit confirmation first.

---

## Quick start (after one-time setup below)

Double-click **`start.bat`** in the repo root. It starts Ollama (if needed), the backend, and the frontend in their own windows, then opens the app in your browser. `start.bat tunnel` also starts the Cloudflare tunnel for phone access.

## Requirements

- Windows PC (the backend runs here; macOS/Linux work too, just translate the `.bat` scripts)
- Python 3.10+
- Node.js 20+ (only to run or deploy the frontend)
- [Ollama](https://ollama.com) installed and running
- A Google Cloud OAuth client (Desktop app) — `credentials.json`

## 1. Backend setup (on your PC)

```bat
cd backend
copy .env.example .env
```

Edit `backend/.env`:

- `API_TOKEN` — generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- `ALLOWED_ORIGINS` — keep `http://localhost:3000`; add your Vercel URL later (comma-separated).

Pull the model (~2.6 GB, one time):

```bat
ollama pull qwen3:4b
```

> `qwen3:4b` is the recommended default — the most reliable small model at tool calling.
> Alternatives via `OLLAMA_MODEL` in `.env`: `llama3.2:3b` (smaller/weaker) or `llama3.1:8b` (better, needs ≥12 GB RAM).

Add your Google OAuth client:

1. [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials → Create OAuth client ID → **Desktop app**.
2. Enable the **Gmail API** for the project.
3. Download the JSON and save it as `backend/credentials/credentials.json`.

Start the backend:

```bat
run_backend.bat
```

First run creates a venv and installs dependencies (the embedding model downloads on first sync). The API is then at `http://127.0.0.1:8000`.

## 2. Frontend (local)

```bat
cd frontend
copy .env.local.example .env.local
npm install
npm run dev
```

Open http://localhost:3000, click the **gear icon**, and enter your `API_TOKEN`. Then on the Sync page click **Connect Gmail** — a Google consent window opens on the PC; approve it and the status card flips to connected. Run a sync and start chatting.

## 3. Mobile / remote access

The backend never leaves your PC — your phone reaches it through a tunnel.

**Quick tunnel (no account, URL changes each run):**

```bat
winget install Cloudflare.cloudflared
cd backend
run_tunnel.bat
```

Copy the printed `https://<random>.trycloudflare.com` URL.

**Deploy the UI to Vercel (one time):**

1. Push this repo to GitHub and import it at [vercel.com](https://vercel.com).
2. Set **Root Directory = `frontend`** (framework auto-detects Next.js). Deploy.
3. Add your Vercel URL (e.g. `https://yourapp.vercel.app`) to `ALLOWED_ORIGINS` in `backend/.env` and restart the backend.

**On your phone:** open the Vercel URL → gear icon → paste the tunnel URL as Backend URL + your API token → save. Voice input works in mobile Chrome/Safari (HTTPS via Vercel satisfies the mic requirement).

> **Stable URL (optional):** quick-tunnel URLs rotate on every restart. With a free Cloudflare account and a domain you can create a *named tunnel* (`cloudflared tunnel login` → `create` → `route dns` → `run`), then set `NEXT_PUBLIC_API_URL` permanently in Vercel. See [Cloudflare's docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

### Security model — read this

- Every API route (except a bare health check) requires `Authorization: Bearer <API_TOKEN>`; requests without it get 401. The backend refuses to serve at all if `API_TOKEN` is unset.
- **Leave `NEXT_PUBLIC_API_TOKEN` empty in Vercel.** Anything `NEXT_PUBLIC_` is baked into public JavaScript. Enter the token once per device in the Settings sheet instead (stored in that browser's localStorage only).
- Anyone with both the tunnel URL **and** the token can read/trash your email — treat the token like a password.
- Google sign-in only ever happens in a browser **on the PC**. If the token expires while you're remote, the app shows "finish sign-in on your PC".
- Trashed emails go to Gmail's Trash and are recoverable for 30 days.
- Voice input uses the browser's speech engine (in Chrome, audio is processed by Google's speech service).

## Agent capabilities

Read-only (no confirmation): `search_emails`, `get_emails_by_sender`, `get_emails_by_label`, `count_emails`, `get_inbox_stats`, `get_top_senders`, `list_labels`, `summarize_sender`.

Destructive (always previewed + confirmed by you in the UI, never auto-executed): `trash_emails`, `create_label`, `apply_label`, `create_filter`.

Try: *"What subscriptions email me the most?"*, *"Summarize my emails from chess.com"*, *"Trash all my promotions emails"* (you'll get a preview + confirm card).

## Repo layout

```
backend/   FastAPI server — Gmail OAuth, ChromaDB index, Ollama agent (SSE APIs)
  app/routers/   status, gmail, sync, emails, chat endpoints
  app/agent/     tool schemas/executors, streaming agent loop, prompts
  run_backend.bat / run_tunnel.bat
frontend/  Next.js 16 app — /sync and /assistant pages (all client components)
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Status card: "Ollama not running" | `ollama serve` (or launch the Ollama app) |
| Status card: model not found | `ollama pull qwen3:4b` |
| 401 in the UI | Token in Settings doesn't match `API_TOKEN` in `backend/.env` |
| Phone can't reach backend | Tunnel restarted → new URL; re-paste it in Settings |
| CORS error in browser console | Add the frontend's origin to `ALLOWED_ORIGINS` and restart the backend |
| "Finish sign-in on your PC" persists | Complete the Google consent window at the PC, or delete `backend/credentials/token.json` and reconnect |
