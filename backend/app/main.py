"""
main.py — FastAPI application factory and ASGI entrypoint.

Run with:  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
(see run_backend.bat).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers import chat, emails, gmail, status, sync


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
    app.include_router(sync.router)
    app.include_router(emails.router)
    app.include_router(chat.router)

    return app


app = create_app()
