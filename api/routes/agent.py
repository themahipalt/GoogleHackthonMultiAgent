"""
Agent routes — run the orchestrator and stream results.

POST /run           → collect all SSE events, return as JSON list
GET  /stream        → SSE stream (real-time)
GET  /daily-briefing → SSE stream for the daily briefing workflow
"""
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agents import run_orchestrator
from api.schemas import RunRequest

router = APIRouter(tags=["agent"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_DAILY_BRIEFING_MSG = (
    "Give me a daily briefing: list my pending tasks and today's calendar events. "
    "Summarize them clearly."
)


@router.post("/run")
async def run(req: RunRequest):
    """Non-streaming: run the full workflow and return the complete event log."""
    events = []
    async for chunk in run_orchestrator(req.message, req.user_id):
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:]))
    return {"events": events}


@router.get("/stream")
async def stream(message: str, user_id: str = "demo"):
    """SSE streaming — real-time agent activity feed."""
    return StreamingResponse(
        run_orchestrator(message, user_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/daily-briefing")
async def daily_briefing(user_id: str = "demo"):
    """SSE stream — pending tasks + today's events summary."""
    return StreamingResponse(
        run_orchestrator(_DAILY_BRIEFING_MSG, user_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
