"""
Google API credential helpers.

Two auth strategies are supported:

1. Service Account (for Calendar write access via sharing)
   → Set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON file.
   → Share your Google Calendar with the service account email.

2. OAuth 2.0 (for Google Tasks API — user's own tasks)
   → Run:  python auth/oauth_setup.py
   → This writes tokens/tasks_token.json used here.
"""
import os
from functools import lru_cache

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_TASKS_SCOPES    = ["https://www.googleapis.com/auth/tasks"]


@lru_cache(maxsize=1)
def get_calendar_service():
    """
    Return an authenticated Google Calendar API service.
    Uses the service account at GOOGLE_APPLICATION_CREDENTIALS.
    Returns None if credentials are not configured.
    """
    creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_file or not os.path.exists(creds_file):
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            creds_file, scopes=_CALENDAR_SCOPES
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def get_tasks_service():
    """
    Return an authenticated Google Tasks API service using OAuth 2.0.
    Returns None if the token file is not configured or is invalid.
    """
    token_path = os.getenv("GOOGLE_TASKS_TOKEN", "./tokens/tasks_token.json")
    client_secrets = os.getenv("GOOGLE_CLIENT_SECRETS", "./auth/client_secrets.json")

    if not os.path.exists(token_path):
        return None

    creds = Credentials.from_authorized_user_file(token_path, _TASKS_SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds, token_path)

    if not creds.valid:
        return None

    return build("tasks", "v1", credentials=creds, cache_discovery=False)


def _save_token(creds: Credentials, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(creds.to_json())
