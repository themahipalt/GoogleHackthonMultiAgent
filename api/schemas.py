"""Pydantic request / response schemas for all API endpoints."""
from pydantic import BaseModel


class RunRequest(BaseModel):
    message: str
    user_id: str = "demo"


class TaskCreateRequest(BaseModel):
    name: str
    priority: str = "medium"    # low | medium | high
    due_date: str | None = None


class EventCreateRequest(BaseModel):
    name: str
    start_time: str             # ISO 8601
    duration_minutes: int = 60
