"""
Task Agent — schemas + handlers.

Storage strategy (auto-selected at runtime):
  1. Google Tasks API  →  if OAuth token is configured (GOOGLE_TASKS_TOKEN)
  2. Cloud Firestore   →  fallback (always available)

Exposed tools: task_create, task_list, task_update, task_delete, task_search

Calendar sync:
  - task_create with due_date/due_time → also creates a linked calendar event
  - task_delete → also deletes the linked calendar event (if any)
"""
from datetime import datetime, timezone
from auth import get_tasks_service
from db import get_db, TASKS
from tools import calendar_tools

# ── Schemas (Gemini FunctionDeclaration-compatible JSON Schema) ───────────────
SCHEMAS = [
    {
        "name": "task_create",
        "description": "Create a new task for the user. If a due_date is provided, a linked calendar event is automatically created. If due_time is also provided (e.g. '09:00'), the calendar event will use that time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":     {"type": "string",  "description": "Task name / description"},
                "priority": {"type": "string",  "enum": ["low", "medium", "high"]},
                "due_date": {"type": "string",  "description": "Due date, e.g. '2026-04-01' or 'tomorrow'"},
                "due_time": {"type": "string",  "description": "Optional time for the calendar event, 24h format e.g. '09:00' or '14:30'. Defaults to '09:00' if due_date is set."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "task_list",
        "description": "List tasks for the user, optionally filtered by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "done", "all"]},
            },
        },
    },
    {
        "name": "task_update",
        "description": "Mark a task done, change its priority, or rename it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id":  {"type": "string",  "description": "ID of the task to update"},
                "status":   {"type": "string",  "enum": ["pending", "done"]},
                "priority": {"type": "string",  "enum": ["low", "medium", "high"]},
                "name":     {"type": "string",  "description": "New task name"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "task_delete",
        "description": "Permanently delete a task by ID. Also deletes the linked calendar event if one was created.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the task to delete"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "task_search",
        "description": "Search tasks by keyword in the task name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search for"},
            },
            "required": ["query"],
        },
    },
]


# ── Handlers ──────────────────────────────────────────────────────────────────

def create(inp: dict, user_id: str) -> dict:
    svc = get_tasks_service()
    result = _gtasks_create(svc, inp, user_id) if svc else _firestore_create(inp, user_id)

    # Auto-create a linked calendar event when a due date is provided
    if inp.get("due_date"):
        resolved = calendar_tools._resolve_date(inp["due_date"])
        if resolved:
            time_str = inp.get("due_time", "09:00")
            cal_inp = {
                "name": inp["name"],
                "start_time": f"{resolved}T{time_str}:00",
                "duration_minutes": 60,
                "description": f"Linked to task #{result.get('task_id', '')}",
            }
            cal_result = calendar_tools.create_event(cal_inp, user_id)
            cal_event_id = cal_result.get("event_id")
            result["calendar_event_id"] = cal_event_id
            # Persist the link so delete can cascade
            if cal_event_id:
                get_db().collection(TASKS).document(result["task_id"]).update(
                    {"calendar_event_id": cal_event_id}
                )

    return result


def list_tasks(inp: dict, user_id: str) -> dict:
    svc = get_tasks_service()
    if svc:
        return _gtasks_list(svc, inp, user_id)
    return _firestore_list(inp, user_id)


def update(inp: dict, user_id: str) -> dict:
    svc = get_tasks_service()
    if svc:
        return _gtasks_update(svc, inp, user_id)
    return _firestore_update(inp, user_id)


def delete(inp: dict, user_id: str) -> dict:
    # Look up the linked calendar event before deleting the task
    task_id = inp["task_id"]
    cal_event_id = _get_calendar_event_id(task_id)

    svc = get_tasks_service()
    result = _gtasks_delete(svc, inp, user_id) if svc else _firestore_delete(inp, user_id)

    # Cascade-delete the linked calendar event
    if cal_event_id:
        cal_result = calendar_tools.delete_event({"event_id": cal_event_id}, user_id)
        result["calendar_event_deleted"] = cal_result.get("deleted", False)
        result["calendar_event_id"] = cal_event_id

    return result


def search(inp: dict, user_id: str) -> dict:
    kw = inp["query"].lower()
    db = get_db()
    docs = db.collection(TASKS).where("user_id", "==", user_id).stream()
    hits = [{"id": d.id, **d.to_dict()} for d in docs
            if kw in d.to_dict().get("name", "").lower()]
    return {"tasks": hits, "count": len(hits)}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_calendar_event_id(task_id: str) -> str | None:
    """Fetch the linked calendar_event_id from Firestore for a given task."""
    doc = get_db().collection(TASKS).document(task_id).get()
    if doc.exists:
        return doc.to_dict().get("calendar_event_id")
    return None


# ── Google Tasks API backend ──────────────────────────────────────────────────

def _gtasks_create(svc, inp: dict, user_id: str) -> dict:
    body = {"title": inp["name"], "notes": f"priority:{inp.get('priority','medium')}"}
    if inp.get("due_date"):
        body["due"] = inp["due_date"] + "T00:00:00.000Z"
    task = svc.tasks().insert(tasklist="@default", body=body).execute()
    _mirror_to_firestore(task["id"], inp, user_id, "pending")
    return {"created": True, "task_id": task["id"], "name": task["title"],
            "source": "google_tasks"}


def _gtasks_list(svc, inp: dict, user_id: str) -> dict:
    show_completed = inp.get("status") in ("done", "all")
    result = svc.tasks().list(
        tasklist="@default",
        showCompleted=show_completed,
        maxResults=50,
    ).execute()
    items = result.get("items", [])
    tasks = [{"id": t["id"], "name": t["title"],
               "status": "done" if t.get("status") == "completed" else "pending",
               "due_date": t.get("due", "")[:10] if t.get("due") else None,
               "source": "google_tasks"}
             for t in items]
    return {"tasks": tasks, "count": len(tasks)}


def _gtasks_update(svc, inp: dict, user_id: str) -> dict:
    task = svc.tasks().get(tasklist="@default", task=inp["task_id"]).execute()
    if inp.get("name"):
        task["title"] = inp["name"]
    if inp.get("status") == "done":
        task["status"] = "completed"
    elif inp.get("status") == "pending":
        task["status"] = "needsAction"
    svc.tasks().update(tasklist="@default", task=inp["task_id"], body=task).execute()
    _firestore_update(inp, user_id)
    return {"updated": True, "task_id": inp["task_id"], "source": "google_tasks"}


def _gtasks_delete(svc, inp: dict, user_id: str) -> dict:
    svc.tasks().delete(tasklist="@default", task=inp["task_id"]).execute()
    _firestore_delete(inp, user_id)
    return {"deleted": True, "task_id": inp["task_id"], "source": "google_tasks"}


def _mirror_to_firestore(task_id: str, inp: dict, user_id: str, status: str):
    get_db().collection(TASKS).document(task_id).set({
        "user_id": user_id,
        "name": inp["name"],
        "priority": inp.get("priority", "medium"),
        "due_date": inp.get("due_date"),
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ── Firestore backend ─────────────────────────────────────────────────────────

def _firestore_create(inp: dict, user_id: str) -> dict:
    db = get_db()
    data = {
        "user_id": user_id,
        "name": inp["name"],
        "priority": inp.get("priority", "medium"),
        "due_date": inp.get("due_date"),
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _, ref = db.collection(TASKS).add(data)
    return {"created": True, "task_id": ref.id, "name": data["name"],
            "source": "firestore"}


def _firestore_list(inp: dict, user_id: str) -> dict:
    status_filter = inp.get("status", "all")
    db = get_db()
    docs = db.collection(TASKS).where("user_id", "==", user_id).stream()
    tasks = [{"id": d.id, **d.to_dict()} for d in docs]
    if status_filter != "all":
        tasks = [t for t in tasks if t.get("status") == status_filter]
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return {"tasks": tasks, "count": len(tasks)}


def _firestore_update(inp: dict, user_id: str) -> dict:
    db = get_db()
    ref = db.collection(TASKS).document(inp["task_id"])
    doc = ref.get()
    if not doc.exists:
        return {"error": f"Task {inp['task_id']} not found"}
    patch = {}
    if "status"   in inp: patch["status"]   = inp["status"]
    if "priority" in inp: patch["priority"] = inp["priority"]
    if "name"     in inp: patch["name"]     = inp["name"]
    ref.update(patch)
    return {"updated": True, "task_id": inp["task_id"]}


def _firestore_delete(inp: dict, user_id: str) -> dict:
    db = get_db()
    ref = db.collection(TASKS).document(inp["task_id"])
    if not ref.get().exists:
        return {"error": f"Task {inp['task_id']} not found"}
    ref.delete()
    return {"deleted": True, "task_id": inp["task_id"]}


# ── Dispatch map ──────────────────────────────────────────────────────────────
HANDLERS = {
    "task_create": create,
    "task_list":   list_tasks,
    "task_update": update,
    "task_delete": delete,
    "task_search": search,
}
