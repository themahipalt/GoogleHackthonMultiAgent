"""
Calendar event read routes — reads from Cloud Firestore mirror.

GET /events          → list events for a user
GET /events/upcoming → events starting within the next N minutes (default 15)
"""
from datetime import datetime, timedelta, timezone
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


IST = timezone(timedelta(hours=5, minutes=30))

@router.get("/upcoming")
def upcoming_events(user_id: str = "demo", within_minutes: int = 15):
    """Return events whose start_time falls within the next `within_minutes` minutes."""
    now = datetime.now(IST)
    window_end = now + timedelta(minutes=within_minutes)

    db = get_db()
    docs = db.collection(EVENTS).where("user_id", "==", user_id).stream()

    upcoming = []
    for d in docs:
        data = d.to_dict()
        raw = data.get("start_time", "")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            # Naive datetimes are stored as IST local time by the orchestrator
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            # Normalise to IST for comparison
            dt = dt.astimezone(IST)
            if now <= dt <= window_end:
                minutes_away = int((dt - now).total_seconds() / 60)
                upcoming.append({
                    "id": d.id,
                    **data,
                    "minutes_away": minutes_away,
                })
        except ValueError:
            continue

    upcoming.sort(key=lambda e: e.get("start_time", ""))
    return upcoming
