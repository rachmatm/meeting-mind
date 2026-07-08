"""Workflow orchestration endpoint.

Ties together: Upload -> STT -> Summarizer -> Task Splitter -> Notion
Per blueprint section 3.1.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse

from services.hermes.agents.summarizer import summarize_transcript
from services.hermes.agents.task_splitter import create_task_splitter
from services.hermes.agents.reminder import create_reminder_agent
from services.hermes.agents.recap import create_recap_agent
from services.hermes.gateway.schemas import TaskCreate
from services.hermes.repositories import meetings as meetings_repo
from services.hermes.repositories import tasks as tasks_repo
from services.hermes.repositories import projects as projects_repo
from services.hermes.tools.notion import create_meeting_page
from services.hermes.tools.qdrant import add_meeting_to_context
from services.hermes.worker.queue import enqueue_event
from datetime import date


def get_pool(request: Request) -> asyncpg.Pool:
    """Get DB pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool


router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/process/{meeting_id}")
async def process_meeting(
    meeting_id: uuid.UUID,
    project_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Process meeting through full workflow.
    
    Workflow chain:
    1. Get approved meeting transcript
    2. Run Summarizer Agent
    3. Run Task Splitter Agent
    4. Return tasks for PIC confirmation
    
    This is Phase 2.5 - manual trigger before Phase 3 automation.
    """
    async with pool.acquire() as conn:
        # Step 1: Get meeting
        meeting = await meetings_repo.get_by_id(conn, meeting_id)
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        if meeting["status"] != "approved":
            raise HTTPException(status_code=400, detail="Meeting must be approved first")
        
        # Verify project exists
        project = await projects_repo.get_by_id(conn, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        transcript = meeting["transcript"]
    
    # Step 2: Run Summarizer
    summary = await summarize_transcript(transcript)
    
    # Step 3: Run Task Splitter
    task_splitter = create_task_splitter(pool)
    tasks = await task_splitter.split_tasks(summary, project_id)
    
    # Update meeting with summary
    async with pool.acquire() as conn:
        await meetings_repo.update(conn, meeting_id, summary=summary)
    
    return JSONResponse({
        "meeting_id": str(meeting_id),
        "project_id": str(project_id),
        "summary": summary,
        "suggested_tasks": tasks,
        "next_step": "Review tasks and call POST /tasks/confirm to create them",
    })


@router.post("/auto-create-tasks/{meeting_id}")
async def auto_create_tasks(
    meeting_id: uuid.UUID,
    project_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Process meeting and automatically create tasks.
    
    Convenience endpoint that runs full workflow and creates tasks.
    """
    async with pool.acquire() as conn:
        # Get meeting
        meeting = await meetings_repo.get_by_id(conn, meeting_id)
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        if meeting["status"] != "approved":
            raise HTTPException(status_code=400, detail="Meeting must be approved first")
        
        transcript = meeting["transcript"]
    
    # Run summarizer
    summary = await summarize_transcript(transcript)
    
    # Run task splitter
    task_splitter = create_task_splitter(pool)
    tasks = await task_splitter.split_tasks(summary, project_id)
    
    # Create tasks in DB
    tasks_created = 0
    async with pool.acquire() as conn:
        # Update meeting with summary
        await meetings_repo.update(conn, meeting_id, summary=summary)
        
        # Create each task
        for task_data in tasks:
            deadline = None
            if task_data.get("deadline"):
                try:
                    deadline = task_data["deadline"]
                except Exception:
                    pass
            
            pic_id = task_data.get("pic_id")
            if pic_id and isinstance(pic_id, str):
                try:
                    pic_id = uuid.UUID(pic_id)
                except ValueError:
                    pic_id = None
            
            await tasks_repo.create(
                conn,
                project_id=project_id,
                division=task_data["divisi"],
                description=task_data["task"],
                pic_id=pic_id,
                deadline=deadline,
                meeting_id=meeting_id,
                status="todo",
            )
            tasks_created += 1
    
    # Create Notion page with meeting summary and kanban
    notion_result = None
    try:
        async with pool.acquire() as conn:
            project = await projects_repo.get_by_id(conn, project_id)
        
        if project:
            notion_result = await create_meeting_page(
                project_name=project["name"],
                meeting_summary=summary,
                tasks=tasks,
            )
    except Exception as e:
        print(f"Notion integration failed: {e}")
        notion_result = {"error": str(e)}
    
    # Store meeting in Qdrant for project context
    try:
        await add_meeting_to_context(
            str(project_id),
            str(meeting_id),
            summary,
        )
    except Exception as e:
        print(f"Qdrant storage failed: {e}")
    
    notion_url = notion_result.get("page_url") if notion_result and not notion_result.get("error") else None
# --- Reminder endpoints ---

@router.post("/reminders/schedule/{project_id}")
async def schedule_reminders(
    project_id: uuid.UUID,
    days_before: int = 1,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Schedule reminders for tasks with upcoming deadlines."""
    reminder_agent = create_reminder_agent(pool)
    result = await reminder_agent.schedule_reminders(project_id, days_before)
    return JSONResponse(result)


@router.get("/reminders/overdue/{project_id}")
async def get_overdue_escalations(
    project_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Get overdue tasks that need manager escalation."""
    reminder_agent = create_reminder_agent(pool)
    escalations = await reminder_agent.check_overdue(project_id)
    return JSONResponse({"overdue": escalations})


# --- Recap endpoints ---

@router.get("/recap/{project_id}")
async def get_daily_recap(
    project_id: uuid.UUID,
    target_date: str | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Get daily progress recap for a project."""
    recap_agent = create_recap_agent(pool)
    
    target = None
    if target_date:
        target = date.fromisoformat(target_date)
    
    recap = await recap_agent.generate_daily_recap(project_id, target)
    return JSONResponse(recap)


@router.get("/recap")
async def get_all_recaps(
    target_date: str | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Get daily recaps for all projects."""
    recap_agent = create_recap_agent(pool)
    
    target = None
    if target_date:
        target = date.fromisoformat(target_date)
    
    recaps = await recap_agent.generate_project_recaps(target)
    return JSONResponse({"recaps": recaps})


@router.post("/recap/send")
async def send_daily_recap(
    target_date: str | None = None,
    channels: list[str] | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Generate and send daily recap to management."""
    recap_agent = create_recap_agent(pool)
    
    target = None
    if target_date:
        target = date.fromisoformat(target_date)
    
    recaps = await recap_agent.generate_project_recaps(target)
    results = await recap_agent.send_recap_to_management(recaps, channels)
    
    return JSONResponse({
        "sent": results,
        "recaps": recaps,
    })


# --- Async queue-based processing ---

@router.post("/queue/meeting/{meeting_id}/approve-async")
async def approve_meeting_async(
    meeting_id: uuid.UUID,
    project_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Approve meeting and queue for async processing.
    
    This endpoint queues the meeting for worker processing instead
    of running the full workflow synchronously.
    """
    async with pool.acquire() as conn:
        meeting = await meetings_repo.get_by_id(conn, meeting_id)
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        await meetings_repo.update(conn, meeting_id, status="approved", project_id=project_id)
    
    # Queue the event for async processing
    try:
        await enqueue_event("meeting.approved", {
            "meeting_id": str(meeting_id),
            "project_id": str(project_id),
        })
        return JSONResponse({
            "success": True,
            "message": "Meeting approved and queued for processing",
            "meeting_id": str(meeting_id),
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": "Queue unavailable, processing synchronously",
        }, status_code=503)
    
    return JSONResponse({
        "success": True,
        "meeting_id": str(meeting_id),
        "project_id": str(project_id),
        "tasks_created": tasks_created,
        "notion_page_url": notion_url,
        "notion_kanban_id": notion_result.get("kanban_database_id") if notion_result else None,
        "summary": summary,
    })