"""
Calendar Agent — schemas + handlers.

Uses the real Google Calendar API when a service account is configured.
Falls back to Cloud Firestore when credentials are not present.

To enable real Calendar API:
  1. Create a service account in GCP Console
  2. Enable Google Calendar API
  3. Share your calendar with the service account email
  4. Set GOOGLE_APPLICATION_CREDENTIALS=./service-account.json
  5. Set GOOGLE_CALENDAR_ID=<your calendar ID or "primary">

Exposed tools: calendar_create_event, calendar_list_events, calendar_delete_event
"""
import os
from datetime import datetime, timedelta, timezone

from auth import get_calendar_service
from db import get_db, EVENTS

IST = timezone(timedelta(hours=5, minutes=30))

CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# ── Schemas ───────────────────────────────────────────────────────────────────
SCHEMAS = [
    {
        "name": "calendar_create_event",
        "description": "Schedule a new event in Google Calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":             {"type": "string", "description": "Event title"},
                "start_time":       {"type": "string", "description": "ISO 8601 datetime, e.g. '2026-04-01T09:00:00'"},
                "duration_minutes": {"type": "integer", "description": "Duration in minutes, default 60"},
                "description":      {"type": "string", "description": "Optional event description"},
            },
            "required": ["name", "start_time"],
        },
    },
    {
        "name": "calendar_list_events",
        "description": "List Google Calendar events, optionally filtered to a specific day.",
        "input_schema": {
            "type": "object",
            "properties": {
                "day": {"type": "string",
                        "description": "e.g. 'today', 'tomorrow', 'Friday', '2026-04-01'. Omit for all upcoming."},
            },
        },
    },
    {
        "name": "calendar_delete_event",
        "description": "Delete a Google Calendar event by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "ID of the event to delete"},
            },
            "required": ["event_id"],
        },
    },
]


# ── Handlers ──────────────────────────────────────────────────────────────────

def create_event(inp: dict, user_id: str) -> dict:
    svc = get_calendar_service()
    if svc:
        return _gcal_create(svc, inp, user_id)
    return _firestore_create(inp, user_id)


def list_events(inp: dict, user_id: str) -> dict:
    svc = get_calendar_service()
    if svc:
        return _gcal_list(svc, inp)
    return _firestore_list(inp, user_id)


def delete_event(inp: dict, user_id: str) -> dict:
    svc = get_calendar_service()
    if svc:
        return _gcal_delete(svc, inp, user_id)
    return _firestore_delete(inp, user_id)


# ── Google Calendar API backend ───────────────────────────────────────────────

def _gcal_create(svc, inp: dict, user_id: str) -> dict:
    start = inp["start_time"]
    duration = inp.get("duration_minutes", 60)
    end = _add_minutes(start, duration)

    body = {
        "summary": inp["name"],
        "description": inp.get("description", ""),
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end":   {"dateTime": end,   "timeZone": "UTC"},
    }
    event = svc.events().insert(calendarId=CALENDAR_ID, body=body).execute()

    # Mirror to Firestore so /events endpoint stays consistent
    get_db().collection(EVENTS).document(event["id"]).set({
        "user_id":          user_id,
        "name":             inp["name"],
        "start_time":       start,
        "duration_minutes": duration,
        "gcal_id":          event["id"],
        "html_link":        event.get("htmlLink", ""),
        "created_at":       datetime.now(timezone.utc).isoformat(),
    })

    return {
        "created":    True,
        "event_id":   event["id"],
        "name":       inp["name"],
        "start_time": start,
        "html_link":  event.get("htmlLink"),
        "source":     "google_calendar",
    }


def _gcal_list(svc, inp: dict) -> dict:
    date_prefix = _resolve_date(inp.get("day", ""))
    now = datetime.now(timezone.utc)

    # When a specific day is requested, bound the query to [00:00, 23:59] on
    # that day. When no day is given, show everything from now onward (no upper
    # bound) so users see all upcoming events.
    if date_prefix:
        time_min = f"{date_prefix}T00:00:00+05:30"
        time_max = f"{date_prefix}T23:59:59+05:30"
    else:
        time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = None

    kwargs = dict(
        calendarId=CALENDAR_ID,
        timeMin=time_min,
        maxResults=20,
        # singleEvents=True expands recurring events into individual instances
        # so each occurrence appears as a separate item in the results.
        singleEvents=True,
        orderBy="startTime",
    )
    if time_max:
        kwargs["timeMax"] = time_max

    result = svc.events().list(**kwargs).execute()
    items = result.get("items", [])
    events = [
        {
            "id":         e["id"],
            "name":       e.get("summary", ""),
            "start_time": e["start"].get("dateTime", e["start"].get("date", "")),
            "html_link":  e.get("htmlLink", ""),
            "source":     "google_calendar",
        }
        for e in items
    ]
    return {"events": events, "count": len(events), "filter": date_prefix or "upcoming"}


def _gcal_delete(svc, inp: dict, user_id: str) -> dict:
    svc.events().delete(calendarId=CALENDAR_ID, eventId=inp["event_id"]).execute()
    # Remove from Firestore mirror
    get_db().collection(EVENTS).document(inp["event_id"]).delete()
    return {"deleted": True, "event_id": inp["event_id"], "source": "google_calendar"}


# ── Firestore backend ─────────────────────────────────────────────────────────

def _firestore_create(inp: dict, user_id: str) -> dict:
    db = get_db()
    data = {
        "user_id":          user_id,
        "name":             inp["name"],
        "start_time":       inp["start_time"],
        "duration_minutes": inp.get("duration_minutes", 60),
        "description":      inp.get("description", ""),
        "created_at":       datetime.now(timezone.utc).isoformat(),
    }
    _, ref = db.collection(EVENTS).add(data)
    return {"created": True, "event_id": ref.id, "name": data["name"],
            "start_time": data["start_time"], "source": "firestore"}


def _firestore_list(inp: dict, user_id: str) -> dict:
    date_prefix = _resolve_date(inp.get("day", ""))
    db = get_db()
    docs = db.collection(EVENTS).where("user_id", "==", user_id).stream()
    events = [{"id": d.id, **d.to_dict()} for d in docs]
    if date_prefix:
        events = [e for e in events if str(e.get("start_time", "")).startswith(date_prefix)]
    events.sort(key=lambda e: e.get("start_time", ""))
    return {"events": events, "count": len(events), "filter": date_prefix or "all"}


def _firestore_delete(inp: dict, user_id: str) -> dict:
    db = get_db()
    ref = db.collection(EVENTS).document(inp["event_id"])
    if not ref.get().exists:
        return {"error": f"Event {inp['event_id']} not found"}
    ref.delete()
    return {"deleted": True, "event_id": inp["event_id"]}


# ── Date utilities ─────────────────────────────────────────────────────────────

def _resolve_date(day_str: str) -> str | None:
    if not day_str:
        return None
    s = day_str.strip().lower()
    today = datetime.now(IST).date()
    if s == "today":
        return str(today)
    if s == "tomorrow":
        return str(today + timedelta(days=1))
    day_map = {"monday": 0, "tuesday": 1, "wednesday": 2,
               "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    if s in day_map:
        # Compute days until the next occurrence of the named weekday.
        # `% 7` wraps negative differences and gives 0 when today matches;
        # `or 7` replaces 0 with 7 so "friday" on a Friday means next Friday,
        # not today (avoids showing a potentially already-past day).
        diff = (day_map[s] - today.weekday()) % 7 or 7
        return str(today + timedelta(days=diff))
    if len(s) == 10 and s[4] == "-":
        return s
    return None


def _add_minutes(iso_dt: str, minutes: int) -> str:
    """Add N minutes to an ISO 8601 datetime string."""
    try:
        dt = datetime.fromisoformat(iso_dt.replace("Z", "+00:00"))
        return (dt + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return iso_dt  # return unchanged if unparseable


# ── Dispatch map ──────────────────────────────────────────────────────────────
HANDLERS = {
    "calendar_create_event": create_event,
    "calendar_list_events":  list_events,
    "calendar_delete_event": delete_event,
}
