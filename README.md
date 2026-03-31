# 🤖 Multi-Agent Productivity Assistant

A chat-based AI assistant that manages your **tasks**, **calendar events**, and **notes** using plain English. You type a request, Gemini 2.5 Flash figures out what to do, and calls the right tools automatically.

---

## 🚀 Getting Started

```bash
cd /Users/mahipalthakur/agent/GenAiAcademy/Hackthon/Prototype
uvicorn main:app --reload
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

---

## 🖥️ UI Layout

```
┌─────────────────────────────┬───────────────────┐
│  Chat (left)                │  Sidebar (right)  │
│  - Example chips            │  - Tasks list     │
│  - Message history          │  - Calendar list  │
│  - Agent trace (bottom)     │  - Notes list     │
│  - Input + Send button      │                   │
└─────────────────────────────┴───────────────────┘
```

| Area              | Description                                                        |
| ----------------- | ------------------------------------------------------------------ |
| **Chat area**     | Where you type and see responses                                   |
| **Agent trace**   | Real-time log showing which agent is doing what (color-coded)      |
| **Sidebar**       | Live view of your data — auto-refreshes after every request        |
| **Daily Briefing**| Summary of all your pending tasks + today's events                 |

---

## 🧠 The 3 Agents

### 📋 Task Agent (green)

| What to say                              | What happens             |
| ---------------------------------------- | ------------------------ |
| Create a task to review PR by Friday     | Creates task with due date |
| What tasks do I have pending?            | Lists pending tasks      |
| Mark task `abc123` as done               | Updates status to done   |
| Change task `abc123` priority to high    | Updates priority         |
| Delete task `abc123`                     | Permanently removes it   |
| Find tasks about onboarding             | Keyword search           |

**Fields:** name, priority (`low` / `medium` / `high`), status (`pending` / `done`), due date

**Storage:** Google Tasks API (if OAuth token configured) → otherwise Firestore

---

### 📅 Calendar Agent (orange)

| What to say                               | What happens                |
| ----------------------------------------- | --------------------------- |
| Schedule standup tomorrow 9am             | Creates event at 9am next day |
| Book a 2-hour team meeting Friday 2pm    | Creates 120-min event       |
| What's on my calendar today?             | Lists today's events        |
| What's on my calendar this Friday?       | Lists events for that day   |
| Delete event `abc123`                    | Removes it                  |

**Date understanding:** `today`, `tomorrow`, `Monday`–`Sunday`, or `2026-04-15`

**Default event duration:** 60 minutes

**Storage:** Google Calendar API (if service account configured) → otherwise Firestore

---

### 📝 Notes Agent (pink)

| What to say                                            | What happens                          |
| ------------------------------------------------------ | ------------------------------------- |
| Save a note about project ideas: use microservices     | Creates note with title + body        |
| Note tagged work,ideas: Refactor auth module           | Creates tagged note                   |
| Search notes for microservices                         | Keyword search across title/body/tags |
| Delete note `abc123`                                   | Removes it                            |

**Fields:** title, body, tags (comma-separated)

**Storage:** Firestore only

---

## ⚡ Multi-Step Requests

The orchestrator can handle multiple actions in one message:

```
"Schedule standup tomorrow 9am + create prep task"
```

```
→ calendar_create_event(...)    ← runs in parallel
→ task_create(...)              ← runs in parallel
→ Gemini summarizes both results
```

**More examples:**

- `"What tasks do I have? Also show today's calendar"`
- `"Create 3 tasks: design doc, code review, deploy"`
- `"Save a note about today's meeting and schedule followup next Monday"`

---

## 🔍 Agent Trace Panel

Every request shows a real-time trace:

```
[orchestrator]   Processing: Schedule standup tomorrow 9am
[orchestrator]   Hop 1 — model=gemini-2.5-flash
[calendar_agent] → calendar_create_event({"name": "Standup", ...})
[calendar_agent] {"created": true, "event_id": "abc123", ...}
[orchestrator]   ✓ Done.
```

- Each **hop** = one round-trip to Gemini
- **Tool calls** show the exact arguments sent
- **Tool results** show the raw response (truncated to 200 chars)

---

## 🗄️ Storage Modes

The app auto-selects the backend based on available credentials:

| Credential                     | Tasks backend   | Calendar backend    | Notes backend |
| ------------------------------ | --------------- | ------------------- | ------------- |
| Nothing configured             | Firestore       | Firestore           | Firestore     |
| `GOOGLE_TASKS_TOKEN` set       | Google Tasks API| Firestore           | Firestore     |
| `service-account.json` present | Google Tasks API| Google Calendar API | Firestore     |

> **Local demo (no GCP setup):** Just run `gcloud auth application-default login` and Firestore will work as the backend for everything.

---

## 🌐 REST API

Direct access without the chat interface:

```
GET  /tasks?user_id=demo           # List tasks
GET  /events?user_id=demo          # List events
GET  /notes?user_id=demo           # List notes
GET  /logs?user_id=demo            # Agent activity log
GET  /stream?message=...&user_id=  # SSE chat stream
GET  /daily-briefing?user_id=demo  # Briefing SSE stream
GET  /health                       # Server status
```
