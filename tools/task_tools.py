"""
Task Agent — schemas + handlers.

Storage strategy (auto-selected at runtime):
  1. Google Tasks API  →  if OAuth token is configured (GOOGLE_TASKS_TOKEN)
  2. Cloud Firestore   →  fallback (always available)

Exposed tools: task_create, task_list, task_update, task_delete, task_search
"""
from datetime import datetime, timezone
from auth import get_tasks_service
from db import get_db, TASKS

# ── Schemas (Gemini FunctionDeclaration-compatible JSON Schema) ───────────────
SCHEMAS = [
    {
        "name": "task_create",
        "description": "Create a new task for the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":     {"type": "string",  "description": "Task name / description"},
                "priority": {"type": "string",  "enum": ["low", "medium", "high"]},
                "due_date": {"type": "string",  "description": "Due date, e.g. '2026-04-01' or 'tomorrow'"},
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
        "description": "Permanently delete a task by ID.",
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
# Each handler checks whether a live Google Tasks OAuth token exists.
# If yes → delegate to the Google Tasks API backend (real Google Tasks).
# If no  → fall back to Firestore so the app still works without OAuth setup.

def create(inp: dict, user_id: str) -> dict:
    svc = get_tasks_service()
    if svc:
        return _gtasks_create(svc, inp, user_id)
    return _firestore_create(inp, user_id)


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
    svc = get_tasks_service()
    if svc:
        return _gtasks_delete(svc, inp, user_id)
    return _firestore_delete(inp, user_id)


def search(inp: dict, user_id: str) -> dict:
    # Firestore doesn't support full-text search, so we fetch all of the user's
    # tasks and do a case-insensitive substring match in Python. Acceptable for
    # the small data volumes of a personal productivity tool.
    kw = inp["query"].lower()
    db = get_db()
    docs = db.collection(TASKS).where("user_id", "==", user_id).stream()
    hits = [{"id": d.id, **d.to_dict()} for d in docs
            if kw in d.to_dict().get("name", "").lower()]
    return {"tasks": hits, "count": len(hits)}


# ── Google Tasks API backend ──────────────────────────────────────────────────

def _gtasks_create(svc, inp: dict, user_id: str) -> dict:
    body = {"title": inp["name"], "notes": f"priority:{inp.get('priority','medium')}"}
    if inp.get("due_date"):
        # Google Tasks API requires a full RFC 3339 timestamp for the due field
        body["due"] = inp["due_date"] + "T00:00:00.000Z"
    task = svc.tasks().insert(tasklist="@default", body=body).execute()
    # Mirror to Firestore so search() and the /tasks REST endpoint can query
    # tasks regardless of which backend created them.
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
    _firestore_update(inp, user_id)   # keep Firestore mirror in sync
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
    q = db.collection(TASKS).where("user_id", "==", user_id)
    docs = q.stream()
    tasks = [{"id": d.id, **d.to_dict()} for d in docs]
    # Status filter is applied in Python rather than in Firestore to avoid
    # needing a composite index on (user_id, status).
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
