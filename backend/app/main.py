"""
main.py — FastAPI application factory and ASGI entrypoint.

Run with:  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
(see run_backend.bat).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers import gmail, status


def create_app() -> FastAPI:
    """Build and configure the FastAPI app."""
    app = FastAPI(title="GmailManagerRAG")

    # CORS is middleware (not a route dependency) so OPTIONS preflights pass
    # without needing the Authorization header themselves.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(status.router)
    app.include_router(gmail.router)

    # TODO(Phase 2): app.include_router(sync.router)   — sync job/queue + SSE progress + /api/emails
    # TODO(Phase 3): app.include_router(chat.router)   — agent engine + SSE chat + confirmation store

    return app


app = create_app()
