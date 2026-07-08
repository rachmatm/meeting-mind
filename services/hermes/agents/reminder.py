"""Reminder Agent - schedules and sends follow-up notifications to PICs.

Blueprint section 6.3 - Input: Task list with PICs, Output: Scheduled reminders.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import asyncpg

from openai import AsyncOpenAI

from services.hermes.core.settings import get_settings
from services.hermes.repositories import pics as pics_repo
from services.hermes.repositories import tasks as tasks_repo
from services.hermes.repositories import projects as projects_repo


# Output schema per blueprint section 6.3
REMINDER_SCHEMA = {
    "type": "object",
    "properties": {
        "reminders_scheduled": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pic_id": {"type": "string"},
                    "pic_name": {"type": "string"},
                    "person_name": {"type": "string"},
                    "contact_type": {"type": "string"},
                    "contact_value": {"type": "string"},
                    "task_id": {"type": "string"},
                    "task_description": {"type": "string"},
                    "reminder_date": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["pic_id", "pic_name", "person_name", "contact_type", "contact_value", "task_id", "task_description", "reminder_date", "message"],
            },
        }
    },
    "required": ["reminders_scheduled"],
}


class ReminderAgent:
    """Agent for scheduling and sending follow-up notifications."""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def schedule_reminders(
        self,
        project_id: uuid.UUID,
        days_before_deadline: int = 1,
    ) -> dict[str, Any]:
        """Schedule reminders for tasks with upcoming deadlines.
        
        Args:
            project_id: Project to schedule reminders for
            days_before_deadline: Days before deadline to send reminder
            
        Returns:
            Dict with scheduled reminders
        """
        # Get tasks due soon
        async with self.pool.acquire() as conn:
            tasks = await tasks_repo.get_due_soon(conn, days_before_deadline)
            project = await projects_repo.get_by_id(conn, project_id)
        
        project_name = project["name"] if project else "Unknown Project"
        
        reminders = []
        for task in tasks:
            task_dict = dict(task)
            pic_id = task_dict.get("pic_id")
            
            if not pic_id:
                continue
            
            # Get PIC details and contacts
            async with self.pool.acquire() as conn:
                pic = await pics_repo.get_by_id(conn, pic_id)
                if not pic:
                    continue
                
                contacts = await pics_repo.get_contacts(conn, pic_id)
            
            if not contacts:
                continue
            
            # Get primary contact
            primary = next((c for c in contacts if c["is_primary"]), contacts[0])
            
            # Build reminder
            deadline = task_dict.get("deadline")
            reminder_date = deadline - timedelta(days=days_before_deadline) if deadline else date.today()
            
            # Build personalized message
            message = self._build_reminder_message(
                person_name=primary["person_name"],
                task_description=task_dict["description"],
                deadline=str(deadline) if deadline else "TBD",
                project_name=project_name,
            )
            
            reminders.append({
                "pic_id": str(pic_id),
                "pic_name": pic["name"],
                "person_name": primary["person_name"],
                "contact_type": primary["contact_type"],
                "contact_value": primary["contact_value"],
                "task_id": str(task_dict["id"]),
                "task_description": task_dict["description"],
                "reminder_date": reminder_date.isoformat(),
                "message": message,
            })
        
        return {"reminders_scheduled": reminders}
    
    async def check_overdue(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        """Check for overdue tasks and return escalation info.
        
        Args:
            project_id: Project to check
            
        Returns:
            List of overdue items requiring manager escalation
        """
        async with self.pool.acquire() as conn:
            # Get overdue tasks
            overdue = await conn.fetch("""
                SELECT t.*, p.name as pic_name, p.manager_id
                FROM tasks t
                JOIN pics p ON t.pic_id = p.id
                WHERE t.project_id = $1
                  AND t.status != 'done'
                  AND t.deadline < CURRENT_DATE
                ORDER BY t.deadline
            """, project_id)
            
            project = await projects_repo.get_by_id(conn, project_id)
        
        project_name = project["name"] if project else "Unknown Project"
        escalations = []
        
        for task in overdue:
            task_dict = dict(task)
            manager_id = task_dict.get("manager_id")
            
            if manager_id:
                # Get manager info
                async with self.pool.acquire() as conn:
                    manager = await pics_repo.get_by_id(conn, manager_id)
                    manager_contacts = await pics_repo.get_contacts(conn, manager_id)
                
                if manager and manager_contacts:
                    primary = next((c for c in manager_contacts if c["is_primary"]), manager_contacts[0])
                    
                    message = self._build_escalation_message(
                        manager_name=manager["name"],
                        pic_name=task_dict["pic_name"],
                        task_description=task_dict["description"],
                        deadline=str(task_dict["deadline"]),
                        project_name=project_name,
                    )
                    
                    escalations.append({
                        "pic_id": str(task_dict["pic_id"]),
                        "pic_name": task_dict["pic_name"],
                        "manager_id": str(manager_id),
                        "manager_name": manager["name"],
                        "manager_contact": primary["contact_value"],
                        "task_id": str(task_dict["id"]),
                        "task_description": task_dict["description"],
                        "deadline": str(task_dict["deadline"]),
                        "message": message,
                    })
        
        return escalations
    
    async def send_notification(
        self,
        contact_type: str,
        contact_value: str,
        message: str,
    ) -> bool:
        """Send notification via configured channel.
        
        Args:
            contact_type: whatsapp, email, or slack
            contact_value: Phone, email, or Slack ID
            message: Message content
            
        Returns:
            True if sent successfully
        """
        if contact_type == "slack":
            return await self._send_slack(contact_value, message)
        elif contact_type == "whatsapp":
            return await self._send_whatsapp(contact_value, message)
        elif contact_type == "email":
            return await self._send_email(contact_value, message)
        else:
            print(f"Unknown contact type: {contact_type}")
            return False
    
    async def _send_slack(self, user_id: str, message: str) -> bool:
        """Send Slack message."""
        import httpx
        from services.hermes.core.settings import get_settings
        
        settings = get_settings()
        token = settings.slack_bot_token
        
        if not token:
            print("Slack bot token not configured")
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {token.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "channel": user_id,
                        "text": message,
                    },
                )
                result = response.json()
                return result.get("ok", False)
        except Exception as e:
            print(f"Slack send failed: {e}")
            return False
    
    async def _send_whatsapp(self, phone: str, message: str) -> bool:
        """Send WhatsApp message."""
        import httpx
        from services.hermes.core.settings import get_settings
        
        settings = get_settings()
        api_url = settings.whatsapp_api_url
        api_token = settings.whatsapp_api_token
        
        if not api_url or not api_token:
            print("WhatsApp API not configured")
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    api_url.get_secret_value(),
                    headers={
                        "Authorization": f"Bearer {api_token.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "to": phone,
                        "message": message,
                    },
                )
                return response.status_code == 200
        except Exception as e:
            print(f"WhatsApp send failed: {e}")
            return False
    
    async def _send_email(self, email: str, message: str) -> bool:
        """Send email (placeholder - requires email service integration)."""
        # TODO: Implement email sending (SendGrid, AWS SES, etc.)
        print(f"Email to {email}: {message}")
        return True
    
    def _build_reminder_message(
        self,
        person_name: str,
        task_description: str,
        deadline: str,
        project_name: str,
    ) -> str:
        """Build personalized reminder message."""
        return f"""Hi {person_name}! 👋

You have a task pending:

Task: {task_description}
Deadline: {deadline}
Project: {project_name}

Please follow up. Let me know if you need any clarification!

Best regards,
Hermes"""
    
    def _build_escalation_message(
        self,
        manager_name: str,
        pic_name: str,
        task_description: str,
        deadline: str,
        project_name: str,
    ) -> str:
        """Build manager escalation message."""
        return f"""Hi {manager_name}! 👋

This is an escalation - task overdue:

PIC: {pic_name}
Task: {task_description}
Deadline: {deadline}
Project: {project_name}

Please take necessary action.

Best regards,
Hermes"""


def create_reminder_agent(pool: asyncpg.Pool) -> ReminderAgent:
    """Factory function to create ReminderAgent."""
    return ReminderAgent(pool)