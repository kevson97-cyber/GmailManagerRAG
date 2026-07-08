# GmailManagerRAG

Local-first Gmail assistant: a FastAPI backend on your PC (Gmail OAuth, ChromaDB semantic index, Ollama agent with native tool calling) + a mobile-friendly Next.js frontend deployable to Vercel, connected via Cloudflare Tunnel.

> **Rebuild in progress** — full setup and deployment docs land at the end of the rebuild.

## Layout

- `backend/` — FastAPI server: Gmail sync, email index, agent chat (Ollama `qwen3:4b`)
- `frontend/` — Next.js app: **Sync & Index** page + **Assistant** chat page
