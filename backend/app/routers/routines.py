"""
routers/routines.py — status and manual trigger for the Generic-labeling routine.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status

from .. import deps
from ..auth import require_token
from ..models import GenericRoutineStatus, RoutineRunResponse

router = APIRouter(prefix="/api/routines", tags=["routines"], dependencies=[Depends(require_token)])


@router.get("/generic", response_model=GenericRoutineStatus)
async def generic_status() -> GenericRoutineStatus:
    routine = deps.get_generic_routine()
    return GenericRoutineStatus(**await asyncio.to_thread(routine.status))


@router.post(
    "/generic/run",
    response_model=RoutineRunResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
)
async def run_generic() -> RoutineRunResponse:
    """Fire one labeling pass in the background; poll GET /generic for results."""
    routine = deps.get_generic_routine()
    if routine.status()["running"]:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail="Routine is already running"
        )
    gmail = await asyncio.to_thread(deps.get_gmail)
    if not gmail.is_authenticated():
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Gmail is not connected"
        )
    asyncio.create_task(routine.run_once(trigger="manual"))
    return RoutineRunResponse(started=True)
