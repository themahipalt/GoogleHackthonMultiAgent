"""
Notes read routes — reads from Cloud Firestore.

GET /notes → list notes for a user
"""
from fastapi import APIRouter
from db import get_db, NOTES

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("")
def list_notes(user_id: str = "demo"):
    db = get_db()
    docs = db.collection(NOTES).where("user_id", "==", user_id).stream()
    notes = sorted(
        [{"id": d.id, **d.to_dict()} for d in docs],
        key=lambda n: n.get("created_at", ""),
        reverse=True,
    )
    return notes
