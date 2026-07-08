# Meeting Recording AI Workflow Blueprint

## 1. Overview

This system is a multi-agent AI workflow for Bithour Production that transforms
meeting recordings into actionable tasks with automatic PIC assignment, Notion
integration, and reminder automation.

**Workflow Chain:**
1. Meeting Recording Upload → 2. Speech-to-Text → 3. User Approval →
4. Project Selection → 5. Summarizer Agent → 6. Task Splitter Agent →
7. Notion Page Creation → 8. Reminder Agent → 9. Recap Agent

This document specifies the architecture, tech stack, data model, and
implementation timeline for the system.

---

## 2. Architecture

```
User (Meeting Recording)
        |
        v
API Gateway  (FastAPI, authenticated)
        |
   upload + STT processing
        |
        v
OpenClaw Orchestrator (workflow manager)
        |
   +------------------+------------------+------------------+
   |                  |                  |                  |
   v                  v                  v                  v
Summarizer        Task Splitter      Reminder           Recap
  Agent              Agent              Agent              Agent
   |                  |                  |                  |
   +------------------+------------------+------------------+
        |                  |                  |
        v                  v                  v
   Qdrant           Notion API        Slack/WhatsApp
(project memory)   (tasks + kanban)   (notifications)
```

Design principles:

- **Multi-agent orchestration**: Each agent (Summarizer, Task Splitter, Reminder,
  Recap) has dedicated prompt, output schema, and scope. No single large prompt.
- **Project memory isolation**: Qdrant collections filtered by project_id - no
  cross-project context leakage.
- **Structured output**: All agents output JSON schemas validated before proceeding
  to next step.
- **Human-in-the-loop**: Transcription summary requires user approval; PIC
  assignments can be edited before finalization.
- **Provider-agnostic LLM**: OpenAI-compatible endpoint, configurable model.

---

## 3. Flow

### 3.1 Meeting Recording Workflow (Primary)

```
User uploads audio file
   -> API Gateway validates auth + file
   -> STT processing (Whisper API / AssemblyAI)
   -> Return transcription for user review
   -> User approves transcription
   -> User selects/creates project
   -> OpenClaw orchestrator executes workflow:
        [Summarizer] -> [Task Splitter] -> [PIC Assignment] -> [Notion Create]
   -> Reminder Agent schedules follow-up
   -> Recap Agent generates daily summary
```

### 3.2 Step-by-Step Detail

**Step 1: Upload & Transcribe**
- Accept audio file (mp3, wav, m4a, webm)
- Send to STT service (Whisper/AssemblyAI)
- Return text transcript to user

**Step 2: User Approval**
- Display transcription summary
- User approves → proceed to project selection
- User rejects → allow re-upload or manual edit

**Step 3: Project Selection**
- User selects existing project or creates new
- Project_id retrieved/created for isolation

**Step 4: Summarizer Agent**
- Input: Raw transcript
- Output: {summary, key_points[], action_items[]}
- JSON schema validation before next step

**Step 5: Task Splitter Agent**
- Input: Summary
- Output: [{divisi, task, deadline, pic}]
- Uses historical data from Qdrant to suggest PIC

**Step 6: PIC Confirmation**
- Display suggested PICs to user
- User can edit/confirm assignments
- Proceed to Notion creation

**Step 7: Notion Integration**
- Create page with meeting summary
- Create kanban board: To Do | In Progress | Done
- Add tasks with PIC, deadline, status

**Step 8: Reminder Agent**
- Schedule follow-up notifications
- Send to each PIC via Slack/WhatsApp

**Step 9: Recap Agent**
- Daily query of all project tasks
- Generate progress summary
- Send to management

---

## 4. Tech Stack

### 4.1 LLM (Reasoning)

- Provider-agnostic. All agents talk to any OpenAI-compatible Chat
  Completions endpoint. Configurable via `LLM_BASE_URL`, `LLM_API_KEY`,
  `LLM_MODEL` so the model can be swapped without code changes.
- Each agent uses native function/tool calling with `strict: true` schemas.
- Set `max_tokens` appropriately per agent - smaller models for simple tasks
  (reminder formatting), larger models for complex reasoning (summarization).
- Model tiering: cheaper models for simple tasks, premium models for complex reasoning.

### 4.2 Speech-to-Text

- **Primary**: OpenAI Whisper API
- **Alternative**: AssemblyAI (for better mixed-language transcription)
- Audio formats supported: mp3, wav, m4a, webm
- Output: Plain text transcription

### 4.3 Vector Database (Project Memory)

- **Qdrant** for production use
- **Why Qdrant**: Native metadata filtering by project_id, better for
  multi-tenant/multi-project isolation
- Collections:
  - `participant_history`: User roles, past task assignments per project
  - `project_context`: Meeting summaries, decisions per project
- Always filter by `project_id` - never query without filter

### 4.4 Structured Database

- **PostgreSQL** (Neon or self-hosted) for:
  - `pics`: Person-In-Charge master data with responsibilities
  - `projects`: project info + participant links
  - `tasks`: task assignments, PIC, deadlines, status
  - `meetings`: transcripts, summaries
  - `audit_log`: workflow event logging

### 4.5 Application and Orchestration

- **Backend**: FastAPI (async), Python, managed with `uv`
- **Orchestration**: OpenClaw workflow engine + n8n for integration triggers
- **Tool Executor**: Service module with adapters per external API
- **Notion API**: Create pages, databases, kanban boards
- **Notifications**: Slack API / WhatsApp API for reminders

### 4.6 Observability

- LLM tracing: Langfuse. Capture prompt, tool calls, tokens, cost per agent.
- Structured logs: PostgreSQL audit_log table.
- Workflow tracking: OpenClaw state machine logs.

### 4.7 Deployment

- Containerized (Docker)
- Hosting: Railway, Fly.io, or cloud VM
- Gateway and agent workers scale independently
- Secrets in environment variables, never hardcoded

---

## 5. Data Model (PostgreSQL)

```sql
-- PICs (Person-In-Charge) - can be individual or group/team
CREATE TABLE pics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL UNIQUE,  -- unique identifier (e.g., email, slack ID, team name)
    name TEXT NOT NULL,
    type TEXT DEFAULT 'person' CHECK (type IN ('person', 'group')),  -- individual or team
    email TEXT,
    slack_id TEXT,
    divisions TEXT[],  -- e.g., ['engineering', 'design', 'marketing']
    responsibilities TEXT[],  -- e.g., ['frontend', 'backend', 'devops']
    skills TEXT[],  -- e.g., ['react', 'python', 'figma']
    max_concurrent_tasks INT DEFAULT 5,
    manager_id UUID REFERENCES pics(id),  -- direct manager (self-referencing)
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- PIC contact methods (multiple per PIC - for groups, multiple people)
CREATE TABLE pic_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pic_id UUID REFERENCES pics(id) ON DELETE CASCADE,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('whatsapp', 'email', 'slack')),
    contact_value TEXT NOT NULL,  -- phone number, email, slack ID
    person_name TEXT NOT NULL,    -- person's name for polite greeting
    is_primary BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Project-PIC junction (many-to-many)
CREATE TABLE project_pics (
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    pic_id UUID REFERENCES pics(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'member',  -- lead, member, reviewer
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (project_id, pic_id)
);

-- Projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tasks table
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    division TEXT NOT NULL,
    description TEXT NOT NULL,
    pic_id UUID REFERENCES pics(id),  -- FK to PIC
    deadline DATE,
    status TEXT DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'done')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Meetings table
CREATE TABLE meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    transcript TEXT NOT NULL,
    summary JSONB,
    audio_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit log
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_pic ON tasks(pic_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_deadline ON tasks(deadline);
CREATE INDEX idx_meetings_project ON meetings(project_id);
CREATE INDEX idx_audit_event ON audit_log(event_type);
CREATE INDEX idx_pics_manager ON pics(manager_id);
```

---

## 6. Agent Specifications

### 6.1 Summarizer Agent

**Purpose**: Generate meeting summary from raw transcript

**Input**: Raw transcript text

**Output Schema**:
```json
{
  "summary": "string",
  "key_points": ["string"],
  "action_items": ["string"]
}
```

**Tools**: LLM only

**Prompt Template**:
```
Role: You are a professional meeting summarizer.
Context: {transcript}
Instruction: Create a concise summary with key points and action items.
Output Format: JSON with summary, key_points[], action_items[]
Constraint: Output must be valid JSON only.
```

### 6.2 Task Splitter Agent

**Purpose**: Split meeting summary into actionable tasks per division

**Input**: Meeting summary + PIC data from PostgreSQL

**Output Schema**:
```json
{
  "tasks": [
    {
      "divisi": "string",
      "task": "string",
      "deadline": "YYYY-MM-DD or null",
      "pic_id": "uuid"
    }
  ]
}
```

**PIC Assignment Logic**:
```
1. Query project_pics for assigned PICs with their divisions/responsibilities
2. Filter by task division
3. Sort by: least concurrent tasks → relevant skills → past performance
4. If no match: query all pics for best fit based on responsibilities
5. Return top candidate with pic_id
```

**Tools**: LLM + PostgreSQL (pics table) + Qdrant (historical performance)

### 6.3 Reminder Agent

**Purpose**: Schedule and send follow-up notifications to PICs

**Input**: Task list with PICs, deadlines, and contact info

**Output Schema**:
```json
{
  "reminders_scheduled": [
    {
      "pic_id": "uuid",
      "pic_name": "string",
      "person_name": "string",  -- for polite greeting
      "contact_type": "whatsapp|email|slack",
      "contact_value": "string",
      "task_id": "uuid",
      "task_description": "string",
      "reminder_date": "YYYY-MM-DD",
      "message": "string"  -- personalized with greeting
    }
  ]
}
```

**Notification Logic**:
1. **Initial reminder**: Send to PIC 1 day before deadline
2. **Overdue escalation**: If task not completed after deadline, send to direct manager
3. **Manager notification**: Include PIC name and task details in message

**PIC Reminder Message**:
```
Hi {person_name}! 👋

You have a task pending:

Task: {task_description}
Deadline: {deadline}
Project: {project_name}

Please follow up. Let me know if you need any clarification!

Best regards,
Hermes
```

**Manager Escalation Message**:
```
Hi {manager_name}! 👋

This is an escalation - task overdue:

PIC: {pic_name}
Task: {task_description}
Deadline: {deadline}
Project: {project_name}

Please take necessary action.

Best regards,
Hermes
```

**Tools**: LLM + PostgreSQL (pics with manager_id) + Slack API / WhatsApp API

### 6.4 Recap Agent

**Purpose**: Generate daily progress summary for management

**Input**: All tasks updated in last 24 hours per project

**Output Schema**:
```json
{
  "date": "YYYY-MM-DD",
  "project": "string",
  "completed": 5,
  "in_progress": 3,
  "blocked": 1,
  "details": "string"
}
```

**Tools**: LLM + Slack API / Email

---

## 7. Prompt Library Structure

### 7.1 Centralized Prompt Management

- Prompts stored in version-controlled location (Notion or GitHub)
- Each agent has dedicated prompt file
- Structure: Role → Context → Instruction → Output Format → Constraint
- Few-shot examples locked (not changed without review)
- Version tracking for all prompt changes

### 7.2 Validation Layer

- Every agent output validated against JSON schema before next step
- If validation fails: retry with error context, max 2 retries
- Schema failures logged to audit_log

---

## 8. Project Memory Isolation (Qdrant)

### 8.1 Collection Design

**participant_history**:
- `user_id`: string (filterable)
- `project_id`: string (filterable, REQUIRED)
- `role`: string
- `divisions`: string[]
- `past_tasks`: string
- `embedding`: vector(1536)

**project_context**:
- `project_id`: string (filterable, REQUIRED)
- `meeting_id`: string
- `summary`: string
- `key_points`: string[]
- `embedding`: vector(1536)

### 8.2 Query Rules

- NEVER query without project_id filter
- Use `must` conditions for project_id
- Default top_k = 5 for PIC suggestions

---

## 9. Notion Integration

### 9.1 Page Creation

1. Create new page under project database
2. Add meeting summary as content blocks
3. Create child database for kanban board

### 9.2 Kanban Board Structure

Properties:
- Task (title)
- Division (select)
- PIC (person)
- Deadline (date)
- Status (select: To Do, In Progress, Done)

---

## 10. API Surface

### PIC Management
| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `POST /pics` | Create new PIC (person or group) | {pic_id} |
| `GET /pics` | List all PICs | [{id, name, type, divisions, responsibilities}] |
| `GET /pics/{id}` | Get PIC details with contacts | {pic details + contacts} |
| `PUT /pics/{id}` | Update PIC info | {updated_pic} |
| `DELETE /pics/{id}` | Deactivate PIC | {success} |
| `POST /pics/{id}/contacts` | Add contact (whatsapp/email/slack) | {contact_id} |
| `GET /pics/{id}/contacts` | List PIC contacts | [{type, value, is_primary}] |
| `DELETE /pics/{id}/contacts/{contact_id}` | Remove contact | {success} |
| `POST /pics/{id}/projects` | Assign PIC to project | {project_pic_id} |
| `GET /pics/available` | Get available PICs by division/responsibility | [{pic}] |

### Project Management
| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `POST /projects` | Create new project | {project_id} |
| `GET /projects` | List projects | [{id, name}] |
| `GET /projects/{id}` | Get project with PICs | {project details} |
| `POST /projects/{id}/pics` | Add PICs to project | {success} |

### Workflow
| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `POST /upload` | Upload meeting audio | {transcript_id} |
| `GET /transcript/{id}` | Get transcription | {transcript, status} |
| `POST /transcript/{id}/approve` | Approve transcription | {project_id} |
| `POST /tasks/confirm` | Confirm PIC assignments | {notion_page_url} |
| `GET /health` | Liveness check | 200 / 503 |

---

## 11. Implementation Timeline (8 weeks)

### Week 1 - Discovery & Architecture
- Finalize prompt structure
- Design project_id/namespace
- Setup OpenClaw environment
- Define JSON schemas for all agents

### Week 2 - STT + Summarizer
- Audio upload endpoint
- Whisper/AssemblyAI integration
- Summarizer Agent with structured output
- Output schema validation

### Week 3 - Task Splitter + Notion
- Task Splitter Agent
- PIC suggestion from Qdrant
- Notion API: page creation + kanban
- User PIC confirmation UI

### Week 4 - Reminder Agent
- Slack/WhatsApp API integration
- Follow-up logic
- Deadline tracking

### Week 5 - Recap + Orchestrator
- Recap Agent for daily summaries
- OpenClaw/n8n orchestration wiring
- End-to-end workflow test

### Week 6 - Context Isolation
- Qdrant setup with project_id filtering
- Ensure no cross-project memory leak
- Test isolation with multiple projects

### Week 7 - Output Formatting & QA
- JSON → Notion block rendering
- Schema validation layer
- Error handling and retries

### Week 8 - Testing & Deployment
- End-to-end testing
- Model tiering optimization
- Caching strategy
- Production deployment

---

## 12. Module Layout

```
services/hermes/
  gateway/
    main.py              # FastAPI app, lifespan
    routes/
      upload.py          # POST /upload - audio file handling
      transcript.py      # GET /transcript, POST /approve
      projects.py        # GET /projects, POST /projects
      tasks.py           # POST /tasks/confirm
      health.py          # GET /health
    security.py          # Auth validation
    schemas.py           # Pydantic models
  agents/
    summarizer.py        # Summarizer Agent
    task_splitter.py     # Task Splitter Agent
    reminder.py          # Reminder Agent
    recap.py             # Recap Agent
  orchestrator/
    workflow.py          # OpenClaw workflow definition
    state.py             # Workflow state machine
  tools/
    stt.py               # Whisper/AssemblyAI client
    notion.py            # Notion API client
    slack.py             # Slack API client
    whatsapp.py          # WhatsApp API client
    qdrant.py            # Qdrant client
  core/
    settings.py          # pydantic-settings
    db.py                # asyncpg pool
    llm.py               # OpenAI-compatible client
  repositories/
    pics.py              # PIC CRUD + availability lookup
    project_pics.py      # Project-PIC associations
    projects.py
    tasks.py
    meetings.py
    audit_log.py
  observability/
    tracing.py           # Langfuse wrapper
```

---

## 13. Status

- [x] Architecture defined
- [x] Audio upload + STT integration
- [x] Agent prompt library
- [x] Output schema validation
- [x] Notion integration (page + kanban)
- [x] Qdrant project isolation
- [x] Reminder + Recap agents
- [x] Worker automation (pgmq + executor)
- [ ] Production deployment

This system prioritizes control over chaos, observability over magic, and
deterministic behavior over creativity.