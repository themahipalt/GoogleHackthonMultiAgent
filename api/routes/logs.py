"""
Agent execution log routes — reads from Cloud Firestore.

GET /logs → last 50 agent tool-call records for a user
"""
from fastapi import APIRouter
from db import get_db, AGENT_LOGS

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("")
def list_logs(user_id: str = "demo"):
    db = get_db()
    docs = db.collection(AGENT_LOGS).where("user_id", "==", user_id).stream()
    logs = sorted(
        [{"id": d.id, **d.to_dict()} for d in docs],
        key=lambda l: l.get("created_at", ""),
        reverse=True,
    )
    return logs[:50]
