"""
auth.py — Bearer-token authentication dependency.

Every route except /api/health depends on `require_token`. The comparison
uses `secrets.compare_digest` to avoid timing side-channels. If API_TOKEN is
unset in the environment, the dependency fails closed (503) rather than
silently allowing every request through.
"""
import secrets

from fastapi import Header, HTTPException, status

from . import config


async def require_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: require a valid `Authorization: Bearer <token>` header."""
    if not config.API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server misconfigured: API_TOKEN is not set in backend/.env",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    provided = authorization.removeprefix("Bearer ").strip()

    if not secrets.compare_digest(provided, config.API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
