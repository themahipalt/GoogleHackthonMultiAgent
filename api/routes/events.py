"""
Calendar event read routes — reads from Cloud Firestore mirror.

GET /events → list events for a user (Firestore mirror of Google Calendar)
"""
from fastapi import APIRouter
from db import get_db, EVENTS

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def list_events(user_id: str = "demo"):
    db = get_db()
    docs = db.collection(EVENTS).where("user_id", "==", user_id).stream()
    events = sorted(
        [{"id": d.id, **d.to_dict()} for d in docs],
        key=lambda e: e.get("start_time", ""),
    )
    return events
