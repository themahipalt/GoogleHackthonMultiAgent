"""
Orchestrator Agent — powered by Gemini 2.0 Flash (google-genai SDK).

Agentic loop:
  1. Send user message to Gemini with all tool schemas.
  2. Execute any function_call parts via dispatch_tool().
  3. Return function responses to Gemini.
  4. Repeat until Gemini produces a final text reply (no more tool calls).

Yields SSE-formatted strings for real-time streaming to the browser.
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator

from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv

from db import get_db, AGENT_LOGS
from tools import GEMINI_TOOLS, dispatch_tool

load_dotenv()

MODEL    = "gemini-2.5-flash"
# Safety cap: prevents infinite tool-call loops if the model never stops
# calling tools. 8 hops allows deeply nested multi-step workflows while
# bounding runaway API costs.
MAX_HOPS = 8

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazy-initialize the Gemini client so the module can be imported without a key set."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client

SYSTEM_PROMPT = (
    "You are the Orchestrator Agent in a multi-agent productivity system "
    "built entirely on Google Cloud.\n"
    "You coordinate three specialist sub-agents via tool calls:\n\n"
    "  - Task Agent      → task_create, task_list, task_update, task_delete, task_search\n"
    "                      (backed by Google Tasks API + Cloud Firestore)\n"
    "  - Calendar Agent  → calendar_create_event, calendar_list_events, calendar_delete_event\n"
    "                      (backed by Google Calendar API + Cloud Firestore)\n"
    "  - Notes Agent     → notes_create, notes_search, notes_delete\n"
    "                      (backed by Cloud Firestore)\n\n"
    "Routing rules — use the RIGHT agent for each request:\n"
    "  • Calendar Agent: use for EVENTS that happen at a specific date/time — meetings, calls,\n"
    "    standups, appointments, interviews, sessions, classes, etc. Any request containing\n"
    "    scheduling language ('schedule', 'book', 'set up a meeting') → calendar_create_event.\n"
    "  • Task Agent: use for ACTION ITEMS and to-dos. If the user provides a due date, always\n"
    "    pass due_date. If they also mention a specific time (e.g. '9 AM', '2:30 PM'), pass\n"
    "    due_time in 24h format (e.g. '09:00', '14:30') — a linked calendar event is created\n"
    "    automatically. Do NOT call calendar_create_event separately for task due times.\n"
    "  • When the user says 'schedule standup AND create prep task', create BOTH a\n"
    "    calendar_create_event AND a task_create (with due_date/due_time for the task).\n\n"
    "General rules:\n"
    "- Always call tools rather than fabricating data.\n"
    "- Batch independent tool calls in a single response when possible.\n"
    "- After all tools complete, return a concise, friendly summary.\n"
)


IST = timezone(timedelta(hours=5, minutes=30))


def _build_config() -> genai_types.GenerateContentConfig:
    """Build a fresh config with the current IST timestamp on every request."""
    now_ist = datetime.now(IST).strftime("%A, %Y-%m-%d %I:%M %p")
    system = SYSTEM_PROMPT + f"- Current date and time: {now_ist} IST (Asia/Kolkata, UTC+5:30).\n"
    return genai_types.GenerateContentConfig(
        system_instruction=system,
        tools=GEMINI_TOOLS,
        # Disable thinking mode — Gemini 2.5 Flash with thinking enabled
        # consumes tool results in thought parts and emits no final text,
        # leaving the user with an empty response.
        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
    )


async def run(message: str, user_id: str) -> AsyncGenerator[str, None]:
    """
    Agentic loop — yields SSE strings.
    Each payload: {"agent": str, "msg": str, "ts": float}
    """
    chat = _get_client().chats.create(model=MODEL, config=_build_config())
    yield _sse("orchestrator", f"Processing: {message}")

    response = chat.send_message(message)

    # Each iteration = one round-trip to Gemini. The loop continues as long as
    # Gemini returns function_call parts; it breaks when Gemini produces only
    # text (meaning it has no more tools to call and is done reasoning).
    for hop in range(MAX_HOPS):
        yield _sse("orchestrator", f"Hop {hop + 1} — model={MODEL}")

        # ── Collect text and function_call parts ──────────────────────────────
        candidates = response.candidates or []
        if not candidates:
            yield _sse("orchestrator", "No candidates in response")
            break
        candidate = candidates[0]
        content = candidate.content
        parts = content.parts if content else None
        import sys
        print(f"[DEBUG hop={hop}] finish={candidate.finish_reason} content={content} parts={parts}", file=sys.stderr, flush=True)
        # Filter out thought parts — only keep real answer/function-call parts
        real_parts = [p for p in parts if not getattr(p, "thought", False)] if parts else []
        if not real_parts:
            # Gemini 2.5 Flash thinking model may return only thought parts or
            # empty parts on final STOP. Try response.text as fallback.
            try:
                text = response.text
                if text:
                    yield _sse("orchestrator", text)
            except Exception:
                yield _sse("orchestrator", f"Empty response (finish_reason={candidate.finish_reason})")
            break
        parts = real_parts

        function_calls = []
        for part in parts:
            # Skip thought parts — these are Gemini's internal reasoning and
            # should not be shown to the user as a final response.
            if part.text and not getattr(part, "thought", False):
                yield _sse("orchestrator", part.text)
            if part.function_call:
                function_calls.append(part.function_call)

        if not function_calls:
            break  # Gemini finished — no more tool calls

        # ── Execute each tool call ────────────────────────────────────────────
        response_parts = []
        last_tool_results = []
        for fc in function_calls:
            agent_label = _agent_label(fc.name)
            args = dict(fc.args)
            yield _sse(agent_label, f"→ {fc.name}({json.dumps(args, ensure_ascii=False)[:100]})")

            result = await dispatch_tool(fc.name, args, user_id)

            yield _sse(agent_label, json.dumps(result)[:200])
            _persist_log(user_id, agent_label, fc.name, result)
            last_tool_results.append((fc.name, result))

            response_parts.append(
                genai_types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result},
                )
            )

        # ── Send all tool results back to Gemini ──────────────────────────────
        # All function responses are sent in a single message so Gemini can
        # reason over parallel tool results at once before the next hop.
        response = chat.send_message(response_parts)

        # ── Check if Gemini returned empty response after tool call ───────────
        # Gemini 2.5 Flash thinking model sometimes processes the result
        # internally (in thought parts) without emitting final text. When that
        # happens, synthesize a readable summary from the tool results so the
        # user sees real data instead of a generic fallback message.
        _candidates = response.candidates or []
        if _candidates:
            _content = _candidates[0].content
            _parts = _content.parts if _content else None
            # Exclude thought parts — only real answer text counts
            _has_text = any(p.text and not getattr(p, "thought", False) for p in _parts) if _parts else False
            _has_fn = any(p.function_call for p in _parts) if _parts else False
            if not _has_text and not _has_fn:
                try:
                    _text = response.text
                except Exception:
                    _text = ""
                if not _text:
                    _text = _synthesize_summary(last_tool_results)
                if _text:
                    yield _sse("orchestrator", _text)
                break

    yield _sse("orchestrator", "✓ Done.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sse(agent: str, msg: str) -> str:
    payload = json.dumps({"agent": agent, "msg": msg, "ts": time.time()})
    return f"data: {payload}\n\n"


def _synthesize_summary(tool_results: list[tuple[str, dict]]) -> str:
    """Build a human-readable summary from tool results when Gemini returns no text."""
    lines = []
    for tool_name, result in tool_results:
        if "events" in result:
            events = result["events"]
            day_filter = result.get("filter", "")
            label = f"today ({day_filter})" if day_filter else "upcoming"
            if not events:
                lines.append(f"No events found for {label}.")
            else:
                lines.append(f"Here are your events for {label}:")
                for e in events:
                    start = e.get("start_time", "")
                    name = e.get("name", e.get("summary", ""))
                    if start:
                        # Format: "2026-04-05T09:00:00" → "09:00"
                        time_part = start[11:16] if len(start) > 10 else start
                        lines.append(f"- **{name}** at {time_part}")
                    else:
                        lines.append(f"- **{name}**")
        elif "tasks" in result:
            tasks = result["tasks"]
            if not tasks:
                lines.append("No tasks found.")
            else:
                lines.append(f"You have {len(tasks)} task(s):")
                for t in tasks[:10]:
                    status = t.get("status", "")
                    name = t.get("name", "")
                    due = t.get("due_date", "")
                    status_icon = "✅" if status == "done" else "⬜"
                    lines.append(f"- {status_icon} **{name}**" + (f" (due {due})" if due else ""))
        elif result.get("created"):
            name = result.get("name", "")
            lines.append(f"✓ Created: **{name}**")
        elif result.get("updated"):
            lines.append(f"✓ Task updated.")
        elif result.get("deleted"):
            lines.append(f"✓ Deleted successfully.")
        elif result.get("error"):
            lines.append(f"⚠️ {result['error']}")
    return "\n".join(lines)


def _agent_label(tool_name: str) -> str:
    # Map a tool function name to a display label so the UI can colour-code
    # activity by sub-agent. "event" tools belong to the calendar agent.
    if "task"     in tool_name: return "task_agent"
    if "calendar" in tool_name: return "calendar_agent"
    if "event"    in tool_name: return "calendar_agent"
    if "note"     in tool_name: return "notes_agent"
    return "orchestrator"


def _persist_log(user_id: str, agent: str, tool: str, result: dict) -> None:
    get_db().collection(AGENT_LOGS).add({
        "user_id":    user_id,
        "agent":      agent,
        "tool":       tool,
        "result":     json.dumps(result),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
