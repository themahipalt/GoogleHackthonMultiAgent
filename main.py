"""
Multi-Agent Productivity Assistant
Powered by: Gemini 2.0 Flash · Cloud Firestore · Google Calendar API · Google Tasks API
Deployed on: Google Cloud Run

Run locally:
    cp .env.example .env        # fill in GOOGLE_API_KEY + GOOGLE_CLOUD_PROJECT
    pip install -r requirements.txt
    uvicorn main:app --reload

Deploy to Cloud Run:
    gcloud run deploy agent-assistant --source . --region us-central1
"""
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from api.routes import agent, tasks, events, notes, logs

load_dotenv()

app = FastAPI(
    title="Multi-Agent Productivity Assistant",
    version="1.0.0",
    description=(
        "Multi-agent AI system powered by Google: "
        "Gemini 2.0 Flash · Cloud Firestore · Google Calendar API · Google Tasks API"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(agent.router)
app.include_router(tasks.router)
app.include_router(events.router)
app.include_router(notes.router)
app.include_router(logs.router)

# ── Utility endpoints ─────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
def health():
    return {
        "status":  "ok",
        "model":   "gemini-2.0-flash",
        "db":      "google-cloud-firestore",
        "time":    datetime.now(timezone.utc).isoformat(),
    }


@app.get("/", response_class=HTMLResponse, tags=["system"])
def ui():
    with open("static/index.html") as f:
        return f.read()
