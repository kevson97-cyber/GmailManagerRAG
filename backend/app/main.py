"""
main.py — FastAPI application factory and ASGI entrypoint.

Run with:  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
(see run_backend.bat).
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, deps
from .routers import chat, emails, gmail, routines, status, sync


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start/stop the Generic-labeling scheduler with the server."""
    task = None
    if config.ROUTINE_INTERVAL_MINUTES > 0:
        task = asyncio.create_task(deps.get_generic_routine().scheduler_loop())
    yield
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    """Build and configure the FastAPI app."""
    app = FastAPI(title="GmailManagerRAG", lifespan=_lifespan)

    # Dev-only convenience: lets `npm run dev` on :3000 call this API. The
    # built app is served same-origin below, so production needs no CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(status.router)
    app.include_router(gmail.router)
    app.include_router(gmail.callback_router)  # unauthenticated /auth/callback (web OAuth)
    app.include_router(sync.router)
    app.include_router(emails.router)
    app.include_router(chat.router)
    app.include_router(routines.router)

    # Static frontend (Next.js `output: "export"` build) served at "/".
    # Mounted last: API routes above always win. html=True serves each
    # directory's index.html and out/404.html for unknown paths.
    if config.STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(config.STATIC_DIR), html=True), name="ui")

    return app


app = create_app()
