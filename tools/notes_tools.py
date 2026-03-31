"""
Notes Agent — schemas + handlers.

Storage: Cloud Firestore (notes collection).
Notes are the best fit for Firestore's document model.

Exposed tools: notes_create, notes_search, notes_delete
"""
from datetime import datetime, timezone
from db import get_db, NOTES

# ── Schemas ───────────────────────────────────────────────────────────────────
SCHEMAS = [
    {
        "name": "notes_create",
        "description": "Save a new note with a title, body text, and optional tags to Firestore.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body":  {"type": "string"},
                "tags":  {"type": "string", "description": "Comma-separated tags, e.g. 'work,ideas'"},
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "notes_search",
        "description": "Search notes by keyword (matches title, body, or tags).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "notes_delete",
        "description": "Delete a note from Firestore by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "Firestore document ID of the note"},
            },
            "required": ["note_id"],
        },
    },
]


# ── Handlers ──────────────────────────────────────────────────────────────────

def create(inp: dict, user_id: str) -> dict:
    db = get_db()
    data = {
        "user_id":    user_id,
        "title":      inp["title"],
        "body":       inp["body"],
        "tags":       inp.get("tags", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _, ref = db.collection(NOTES).add(data)
    return {"created": True, "note_id": ref.id, "title": data["title"],
            "source": "firestore"}


def search(inp: dict, user_id: str) -> dict:
    # Firestore has no native full-text search. We fetch all of the user's
    # notes and do a case-insensitive substring match across title, body, and
    # tags in Python. This is fine for personal-scale note volumes.
    kw = inp["query"].lower()
    db = get_db()
    docs = db.collection(NOTES).where("user_id", "==", user_id).stream()
    hits = []
    for d in docs:
        data = d.to_dict()
        if (kw in data.get("title", "").lower()
                or kw in data.get("body", "").lower()
                or kw in data.get("tags", "").lower()):
            hits.append({"id": d.id, **data})
    return {"results": hits, "count": len(hits)}


def delete(inp: dict, user_id: str) -> dict:
    db = get_db()
    ref = db.collection(NOTES).document(inp["note_id"])
    if not ref.get().exists:
        return {"error": f"Note {inp['note_id']} not found"}
    ref.delete()
    return {"deleted": True, "note_id": inp["note_id"]}


# ── Dispatch map ──────────────────────────────────────────────────────────────
HANDLERS = {
    "notes_create": create,
    "notes_search": search,
    "notes_delete": delete,
}
