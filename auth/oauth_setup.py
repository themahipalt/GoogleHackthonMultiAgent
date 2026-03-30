"""
One-time OAuth 2.0 setup for Google Tasks API.

Run once before starting the server:
    python auth/oauth_setup.py

Prerequisites:
    1. Go to GCP Console → APIs & Services → Credentials
    2. Create an OAuth 2.0 Client ID (Desktop app)
    3. Download as auth/client_secrets.json
    4. Enable the Google Tasks API in your project

This writes tokens/tasks_token.json which the server uses for all Tasks API calls.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/tasks"]
CLIENT_SECRETS = Path("auth/client_secrets.json")
TOKEN_PATH = Path("tokens/tasks_token.json")


def main():
    if not CLIENT_SECRETS.exists():
        print(f"ERROR: {CLIENT_SECRETS} not found.")
        print("Download your OAuth 2.0 credentials from GCP Console and save as auth/client_secrets.json")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
    creds = flow.run_local_server(port=0)

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"Token saved to {TOKEN_PATH}")
    print("You can now start the server with: uvicorn main:app --reload")


if __name__ == "__main__":
    main()
