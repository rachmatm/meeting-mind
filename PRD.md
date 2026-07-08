# Product Requirements Document: Meeting Recording AI Workflow

| Version | Date | Status |
|---------|------|--------|
| 1.0 | 2026-07-08 | Draft |
| 2.0 | 2026-07-08 | Updated based on Bithour Production study case |

---

## 1. Problem Statement

Bithour Production needs an AI assistant for daily project operations that can transform meeting recordings into actionable tasks. Current manual process is time-consuming and error-prone.

**Current Pain Points:**
- **Inconsistent AI results**: No structured prompts, one large prompt handles many tasks
- **Mixed context between projects**: No memory isolation per project/client, all history in one context window
- **General/irrelevant output**: Prompts too generic, no output schema, context not filtered by project

---

## 2. Goals

### Primary Goals
1. **End-to-end meeting workflow**: Upload recording → transcribe → summarize → split tasks → assign PIC → send reminders
2. **Multi-agent orchestration**: Separate specialized agents (Summarizer, Task Splitter, Reminder, Recap) with dedicated prompts
3. **Project memory isolation**: Each project/client has separate namespace with project_id filtering
4. **Structured output**: JSON schema for all agent outputs, directly parsable to Notion/tasks

### Secondary Goals
5. **PIC auto-assignment**: AI assigns Person-In-Charge based on previous project data
6. **User approval flow**: Human-in-the-loop for transcription summary approval before task creation
7. **Notion integration**: Auto-create Notion pages with summary + kanban board for tasks
8. **Reminder automation**: Automatic follow-up notifications to each PIC

---

## 3. Non-Goals

- **Single-agent approach**: Multi-agent workflow required for different output formats
- **Free-text output**: All outputs must be structured JSON, no free-form text
- **Global memory**: No automatic cross-project context sharing
- **Real-time sync responses**: Workflow is asynchronous, not blocking
- **General chatbot**: Scope is meeting-to-task workflow only

---

## 4. User Stories / Use Cases

### Story 1: Meeting Recording to Tasks
**As a** project team member,  
**I want to** upload a meeting recording,  
**So that** AI automatically creates tasks in Notion with proper PIC assignment.

**Flow**:
1. User uploads meeting audio file
2. STT (Whisper/AssemblyAI) transcribes audio → text
3. User reviews and approves transcription summary
4. User inputs/selects project name
5. Task Splitter Agent creates tasks per division with PIC
6. Notion page created with: transcription summary + kanban board (To Do / In Progress / Done)
7. AI suggests PIC based on previous project data
8. User can edit PIC assignments
9. Reminder Agent sends follow-up to each PIC

---

### Story 2: PIC Assignment from Historical Data
**As a** project manager,  
**I want** AI to suggest PICs based on past project data,  
**So that** I don't have to manually assign every task.

**Flow**:
1. When splitting tasks, AI queries vector DB for previous project participants
2. AI matches task type/difficulty to suitable PICs from history
3. If no history exists, AI makes educated guess based on role/availability
4. User reviews and adjusts PIC assignments before finalization

---

### Story 3: Automated Reminders
**As a** team lead,  
**I want** PICs to receive automatic follow-up reminders,  
**So that** tasks don't fall through the cracks.

**Flow**:
1. After task creation, Reminder Agent schedules follow-up
2. At deadline - 1 day, reminder sent to PIC via Slack/WhatsApp
3. If task overdue, escalate to manager
4. Recap Agent sends daily progress summary to management

---

### Story 4: PIC Management
**As an** admin,  
**I want** to manage PICs with their responsibilities and contacts,  
**So that** the system can auto-assign tasks and send notifications.

**Flow**:
1. Create PIC with name, type (person/group), divisions, responsibilities, skills
2. Add multiple contacts (whatsapp, email, slack) with person_name for each
3. Assign direct manager for escalation
4. Link PIC to projects with roles (lead/member/reviewer)
5. System uses this data for auto-assignment and notifications

---

### Story 5: Manager Escalation
**As a** manager,  
**I want** to be notified when my team member's task is overdue,  
**So that** I can take action to keep projects on track.

**Flow**:
1. Task assigned to PIC with deadline
2. Day before deadline: Reminder sent to PIC
3. After deadline: If not completed, escalation sent to PIC's direct manager
4. Manager notification includes: PIC name, task, deadline, project

---

### Story 6: Daily Progress Recap
**As a** management,  
**I want** a daily progress recap of all projects,  
**So that** I stay informed without asking around.

**Flow**:
1. Recap Agent queries all tasks updated in last 24 hours
2. Generates summary: completed, in-progress, blocked tasks
3. Sends to management channel (Slack/Email)

---

## 5. Requirements

### 5.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| F1 | Audio upload endpoint (REST API) | Must |
| F2 | Speech-to-Text integration (Whisper API / AssemblyAI) | Must |
| F3 | Transcription summary with user approval UI | Must |
| F4 | Project selection/input after approval | Must |
| F5 | Summarizer Agent: generates meeting summary | Must |
| F6 | Task Splitter Agent: creates tasks per division with PIC and deadline | Must |
| F7 | Output schema validation before next step | Must |
| F8 | Notion API integration: create page with summary + kanban | Must |
| F9 | PIC auto-assignment based on skills/responsibilities/availability | Must |
| F10 | User can edit/confirm PIC assignments | Must |
| F11 | Reminder Agent: sends follow-up to PICs | Must |
| F12 | Recap Agent: daily progress summary to management | Must |
| F13 | Project_id namespace isolation in vector DB | Must |
| F14 | Multi-agent orchestrator (OpenClaw/n8n) | Must |
| F15 | Prompt library per agent (versioned) | Must |
| F16 | PIC Management: CRUD for PICs with divisions/responsibilities | Must |
| F17 | PIC-Project assignment: link PICs to projects with roles | Must |
| F18 | PIC availability lookup: filter by division/responsibility | Must |
| F19 | PIC contact integration: slack_id, whatsapp for notifications | Must |
| F20 | Manager hierarchy: each PIC has direct manager | Must |
| F21 | Overdue escalation: notify manager when task past deadline | Must |
| F22 | Manager notification includes PIC name and task details | Must |

---

### 5.2 Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NF1 | Audio upload response time | < 5s |
| NF2 | Transcription processing time | < 60s (per minute of audio) |
| NF3 | Full workflow (upload → tasks created) | < 5 min |
| NF4 | Context isolation: no cross-project memory leak | 100% |
| NF5 | Output schema validation success rate | > 99% |
| NF6 | Notion API reliability | > 99% |
| NF7 | Vector DB query with project_id filter | < 500ms |
| NF8 | Containerization | Docker |
| NF9 | Secrets from environment variables | Required |

---

## 6. Workflow Specification

### 6.1 Complete Flow Diagram

```
Meeting Recording Upload
         |
         v
[1] Speech-to-Text (Whisper/AssemblyAI)
         |
         v
[2] User Approval: Transcription Summary
         |
         v
[3] Project Name Input (select/create)
         |
         v
[4] Summarizer Agent -> Meeting Summary
         |
         v
[5] Task Splitter Agent -> Tasks per Division (PIC, Deadline)
         |
         v
[6] User confirms/edits PIC assignments
         |
         v
[7] Notion: Create Page + Kanban Board
         |
         v
[8] Reminder Agent -> Follow-up to each PIC
         |
         v
[9] Recap Agent -> Daily Progress to Management
```

### 6.2 Agent Specifications

| Agent | Input | Output Schema | Tools |
|-------|-------|---------------|-------|
| Summarizer | Raw transcript | {summary: string, key_points: string[], action_items: string[]} | LLM |
| Task Splitter | Summary | [{divisi: string, task: string, deadline: date, pic: string}] | LLM |
| Reminder | Task list | {reminder_sent: boolean, schedule: date[]} | Slack/WhatsApp API |
| Recap | Project tasks (24h) | {completed: int, in_progress: int, blocked: int, details: string} | Slack/Email |

### 6.3 Data Model Requirements

**PICs Table (Person-In-Charge) - can be person or group:**
- id (UUID)
- user_id (string, unique)
- name (string)
- type (enum: person, group)
- divisions (string[])
- responsibilities (string[])
- skills (string[])
- max_concurrent_tasks (int)
- manager_id (UUID, FK to pics) - direct manager for escalation
- is_active (boolean)

**PIC Contacts Table (multiple per PIC):**
- id (UUID)
- pic_id (UUID, FK)
- contact_type (enum: whatsapp, email, slack)
- contact_value (string) - phone number, email, slack ID
- person_name (string) - person's name for polite greeting
- is_primary (boolean) - primary contact for notifications

**Project-PICs Junction:**
- project_id (UUID, FK)
- pic_id (UUID, FK)
- role (lead/member/reviewer)

**Projects Table:**
- id (UUID)
- name (string)
- description (string)
- created_at (timestamp)

**Tasks Table:**
- id (UUID)
- project_id (UUID, FK)
- division (string)
- task_description (string)
- pic_id (UUID, FK to pics)
- deadline (date)
- status (enum: todo, in_progress, done)
- created_at (timestamp)
- updated_at (timestamp)

**Memory/Vectors (Qdrant):**
- project_id metadata filter required
- Collection per data type: participant_history, project_context

---

## 7. Success Metrics

### 7.1 Technical Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| STT accuracy | > 95% | Manual review |
| Task creation success rate | > 95% | Notion API responses |
| PIC suggestion accuracy | > 80% (with history) | User acceptance rate |
| Context isolation | 0% cross-project leaks | QA testing |
| End-to-end latency | < 5 min | Workflow logs |

### 7.2 Business Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| User approval rate (transcription) | > 90% | Approval UI analytics |
| PIC edit rate | < 30% | User modification count |
| Task completion tracking | 100% | Notion status updates |
| Reminder delivery | 100% | Notification logs |

### 7.3 Milestone Checklist

- [ ] Week 1: Discovery & Architecture, prompt library setup
- [ ] Week 2: STT + Summarizer Agent with output schema
- [ ] Week 3: Task Splitter Agent + Notion API integration
- [ ] Week 4: Reminder Agent + Slack/WhatsApp integration
- [ ] Week 5: Recap Agent + orchestrator wiring
- [ ] Week 6: Qdrant project_id isolation setup
- [ ] Week 7: Output formatting, schema validation, QA layer
- [ ] Week 8: Testing, optimization, deployment

---

## 8. Appendix: Technical Stack Reference

See BLUEPRINT.md for complete implementation details including:
- OpenClaw-based multi-agent orchestration
- Qdrant for vector storage with project_id filtering
- Notion API for page + kanban creation
- n8n for workflow orchestration
- Whisper/AssemblyAI for STT
