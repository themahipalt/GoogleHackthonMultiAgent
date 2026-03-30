"""
Task CRUD routes — reads from Cloud Firestore.

GET  /tasks        → list tasks for a user
POST /tasks        → create a task directly (bypasses AI)
"""
from datetime import datetime, timezone
from fastapi import APIRouter
from db import get_db, TASKS
from api.schemas import TaskCreateRequest

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(user_id: str = "demo"):
    db = get_db()
    docs = db.collection(TASKS).where("user_id", "==", user_id).stream()
    tasks = sorted(
        [{"id": d.id, **d.to_dict()} for d in docs],
        key=lambda t: t.get("created_at", ""),
        reverse=True,
    )
    return tasks


@router.post("")
def create_task(body: TaskCreateRequest, user_id: str = "demo"):
    db = get_db()
    data = {
        "user_id":    user_id,
        "name":       body.name,
        "priority":   body.priority,
        "due_date":   body.due_date,
        "status":     "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _, ref = db.collection(TASKS).add(data)
    return {"id": ref.id, **data}
