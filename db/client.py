"""
Google Cloud Firestore client — singleton factory.

Collections used:
  tasks       — user tasks (Firestore or mirrored from Google Tasks API)
  events      — calendar events (mirrored from Google Calendar API)
  notes       — user notes
  agent_logs  — orchestrator tool-call audit trail
"""
import os
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")  # fix c-ares DNS failure on macOS
from google.cloud import firestore

_client: firestore.Client | None = None


def get_db() -> firestore.Client:
    """Return the shared Firestore client, creating it lazily on first call."""
    global _client
    if _client is None:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        # Credentials come from GOOGLE_APPLICATION_CREDENTIALS env var
        # or Application Default Credentials on Cloud Run automatically.
        _client = firestore.Client(project=project)
    return _client


# ── Collection name constants ──────────────────────────────────────────────────
TASKS      = "tasks"
EVENTS     = "events"
NOTES      = "notes"
AGENT_LOGS = "agent_logs"
