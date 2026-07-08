"""Workflow executor - processes events from queue.

Phase 3: Main worker loop that polls queue and executes workflows.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import asyncpg

from services.hermes.core.db import create_pool
from services.hermes.core.settings import get_settings
from services.hermes.worker.queue import get_queue, enqueue_event
from services.hermes.agents.summarizer import summarize_transcript
from services.hermes.agents.task_splitter import create_task_splitter
from services.hermes.agents.reminder import create_reminder_agent
from services.hermes.agents.recap import create_recap_agent
from services.hermes.repositories import meetings as meetings_repo
from services.hermes.repositories import tasks as tasks_repo
from services.hermes.repositories import projects as projects_repo
from services.hermes.tools.notion import create_meeting_page
from services.hermes.tools.qdrant import add_meeting_to_context

log = logging.getLogger("hermes.worker")


class WorkflowExecutor:
    """Executes workflows from queue messages."""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def process_event(self, message: dict[str, Any]) -> bool:
        """Process a single event from the queue.
        
        Args:
            message: Event dict with event_type and payload
            
        Returns:
            True if processed successfully
        """
        event_type = message.get("event_type")
        payload = message.get("payload", {})
        
        log.info(f"Processing event: {event_type}")
        
        try:
            if event_type == "meeting.approved":
                await self._handle_meeting_approved(payload)
            elif event_type == "task.created":
                await self._handle_task_created(payload)
            elif event_type == "reminder.schedule":
                await self._handle_reminder_schedule(payload)
            elif event_type == "recap.daily":
                await self._handle_daily_recap(payload)
            else:
                log.warning(f"Unknown event type: {event_type}")
                return False
            
            return True
            
        except Exception as e:
            log.error(f"Error processing event {event_type}: {e}")
            return False
    
    async def _handle_meeting_approved(self, payload: dict[str, Any]) -> None:
        """Handle meeting approved event - run full workflow."""
        meeting_id = uuid.UUID(payload["meeting_id"])
        project_id = uuid.UUID(payload["project_id"])
        
        # Get meeting transcript
        async with self.pool.acquire() as conn:
            meeting = await meetings_repo.get_by_id(conn, meeting_id)
            if not meeting:
                log.error(f"Meeting not found: {meeting_id}")
                return
            
            transcript = meeting["transcript"]
        
        # Step 1: Summarize
        log.info(f"Summarizing meeting {meeting_id}")
        summary = await summarize_transcript(transcript)
        
        # Step 2: Split tasks
        log.info(f"Splitting tasks for meeting {meeting_id}")
        task_splitter = create_task_splitter(self.pool)
        tasks = await task_splitter.split_tasks(summary, project_id)
        
        # Step 3: Create tasks in DB
        tasks_created = 0
        async with self.pool.acquire() as conn:
            await meetings_repo.update(conn, meeting_id, summary=summary)
            
            for task_data in tasks:
                deadline = task_data.get("deadline")
                pic_id = task_data.get("pic_id")
                
                if pic_id and isinstance(pic_id, str):
                    try:
                        pic_id = uuid.UUID(pic_id)
                    except ValueError:
                        pic_id = None
                
                await tasks_repo.create(
                    conn,
                    project_id=project_id,
                    division=task_data.get("divisi", "operations"),
                    description=task_data.get("task", ""),
                    pic_id=pic_id,
                    deadline=deadline,
                    meeting_id=meeting_id,
                    status="todo",
                )
                tasks_created += 1
        
        log.info(f"Created {tasks_created} tasks for meeting {meeting_id}")
        
        # Step 4: Create Notion page
        try:
            async with self.pool.acquire() as conn:
                project = await projects_repo.get_by_id(conn, project_id)
            
            if project:
                await create_meeting_page(
                    project_name=project["name"],
                    meeting_summary=summary,
                    tasks=tasks,
                )
                log.info(f"Created Notion page for project {project_id}")
        except Exception as e:
            log.error(f"Notion creation failed: {e}")
        
        # Step 5: Store in Qdrant
        try:
            await add_meeting_to_context(str(project_id), str(meeting_id), summary)
            log.info(f"Stored meeting in Qdrant for project {project_id}")
        except Exception as e:
            log.error(f"Qdrant storage failed: {e}")
    
    async def _handle_task_created(self, payload: dict[str, Any]) -> None:
        """Handle task created event - schedule reminder."""
        task_id = uuid.UUID(payload["task_id"])
        
        async with self.pool.acquire() as conn:
            task = await tasks_repo.get_by_id(conn, task_id)
            if not task:
                log.error(f"Task not found: {task_id}")
                return
            
            project_id = task["project_id"]
        
        # Schedule reminder for the task
        reminder_agent = create_reminder_agent(self.pool)
        await reminder_agent.schedule_reminders(project_id, days_before_deadline=1)
        log.info(f"Scheduled reminders for project {project_id}")
    
    async def _handle_reminder_schedule(self, payload: dict[str, Any]) -> None:
        """Handle reminder schedule event."""
        project_id = uuid.UUID(payload["project_id"])
        days_before = payload.get("days_before", 1)
        
        reminder_agent = create_reminder_agent(self.pool)
        result = await reminder_agent.schedule_reminders(project_id, days_before)
        
        # Send notifications
        for reminder in result.get("reminders_scheduled", []):
            await reminder_agent.send_notification(
                reminder["contact_type"],
                reminder["contact_value"],
                reminder["message"],
            )
        
        log.info(f"Sent {len(result.get('reminders_scheduled', []))} reminders")
    
    async def _handle_daily_recap(self, payload: dict[str, Any]) -> None:
        """Handle daily recap event."""
        project_id = payload.get("project_id")
        
        recap_agent = create_recap_agent(self.pool)
        
        if project_id:
            project_uuid = uuid.UUID(project_id)
            recap = await recap_agent.generate_daily_recap(project_uuid)
            recaps = [recap]
        else:
            recaps = await recap_agent.generate_project_recaps()
        
        # Send to management
        await recap_agent.send_recap_to_management(recaps, channels=["slack"])
        log.info(f"Sent daily recap for {len(recaps)} projects")


async def run_worker(poll_interval: float = 5.0) -> None:
    """Run the worker loop.
    
    Args:
        poll_interval: Seconds between queue polls
    """
    log.info("Starting Hermes worker...")
    settings = get_settings()
    pool = await create_pool(settings)
    queue = get_queue()
    executor = WorkflowExecutor(pool)
    
    log.info(f"Worker started, polling queue '{settings.queue_name}'")
    
    try:
        while True:
            # Poll for messages
            message = await queue.dequeue(timeout=poll_interval)
            
            if message:
                msg_id = message["message_id"]
                payload = message["payload"]
                
                log.info(f"Dequeued message {msg_id}: {payload.get('event_type')}")
                
                success = await executor.process_event(payload)
                
                if success:
                    await queue.complete(msg_id)
                    log.info(f"Completed message {msg_id}")
                else:
                    log.warning(f"Failed to process message {msg_id}")
            else:
                # No message, sleep before next poll
                await asyncio.sleep(poll_interval)
                
    except asyncio.CancelledError:
        log.info("Worker cancelled")
    finally:
        await queue.close()
        await pool.close()
        log.info("Worker stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_worker())