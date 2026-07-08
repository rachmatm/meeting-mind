"""Recap Agent - generates daily progress summary for management.

Blueprint section 6.4 - Input: Tasks updated in last 24h, Output: {date, project, completed, in_progress, blocked, details}
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import asyncpg

from openai import AsyncOpenAI

from services.hermes.core.settings import get_settings
from services.hermes.repositories import tasks as tasks_repo
from services.hermes.repositories import projects as projects_repo


# Output schema per blueprint section 6.4
RECAP_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string"},
        "project": {"type": "string"},
        "completed": {"type": "integer"},
        "in_progress": {"type": "integer"},
        "blocked": {"type": "integer"},
        "details": {"type": "string"},
    },
    "required": ["date", "project", "completed", "in_progress", "blocked", "details"],
}


SYSTEM_PROMPT = """You are a project management assistant. Your job is to create concise daily progress summaries.

Instructions:
1. Review the task status counts provided
2. Create a brief, professional summary of project progress
3. Highlight any blocked tasks that need attention
4. Keep the summary concise (2-3 sentences)

Output Format: JSON with the following structure:
{
  "date": "YYYY-MM-DD",
  "project": "project name",
  "completed": 5,
  "in_progress": 3,
  "blocked": 1,
  "details": "summary text here"
}

Constraint: Output must be valid JSON only."""


class RecapAgent:
    """Agent for generating daily progress summaries."""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        settings = get_settings()
        self.client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
        )
        self.model = settings.llm_model
        self.max_tokens = settings.llm_max_tokens
    
    async def generate_daily_recap(
        self,
        project_id: uuid.UUID | None = None,
        target_date: date | None = None,
    ) -> dict[str, Any]:
        """Generate daily progress recap.
        
        Args:
            project_id: Project to generate recap for (None = all projects)
            target_date: Date to generate recap for (default: today)
            
        Returns:
            Dict with recap data
        """
        target_date = target_date or date.today()
        yesterday = target_date - timedelta(days=1)
        
        async with self.pool.acquire() as conn:
            # Get tasks updated in the last 24 hours
            if project_id:
                tasks = await conn.fetch("""
                    SELECT t.*, p.name as project_name
                    FROM tasks t
                    JOIN projects p ON t.project_id = p.id
                    WHERE t.project_id = $1
                      AND t.updated_at >= $2
                    ORDER BY t.updated_at DESC
                """, project_id, yesterday)
                project_name = (await projects_repo.get_by_id(conn, project_id))["name"]
            else:
                tasks = await conn.fetch("""
                    SELECT t.*, p.name as project_name
                    FROM tasks t
                    JOIN projects p ON t.project_id = p.id
                    WHERE t.updated_at >= $1
                    ORDER BY t.updated_at DESC
                """, yesterday)
                project_name = "All Projects"
        
        # Count by status
        completed = sum(1 for t in tasks if t["status"] == "done")
        in_progress = sum(1 for t in tasks if t["status"] == "in_progress")
        todo = sum(1 for t in tasks if t["status"] == "todo")
        
        # Note: "blocked" status needs to be added to the schema
        # For now, we'll treat "todo" that was due before today as potentially blocked
        blocked = 0
        for t in tasks:
            if t["status"] == "todo" and t.get("deadline"):
                try:
                    if t["deadline"] < target_date:
                        blocked += 1
                except Exception:
                    pass
        
        # Build task details for context
        task_details = self._build_task_details(tasks)
        
        # Generate LLM summary if we have tasks
        if tasks:
            summary = await self._generate_summary(
                target_date.isoformat(),
                project_name,
                completed,
                in_progress,
                blocked,
                task_details,
            )
        else:
            summary = f"No tasks updated in the last 24 hours for {project_name}."
        
        return {
            "date": target_date.isoformat(),
            "project": project_name,
            "completed": completed,
            "in_progress": in_progress,
            "blocked": blocked,
            "details": summary,
            "tasks_updated": len(tasks),
        }
    
    async def generate_project_recaps(
        self,
        target_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """Generate recaps for all active projects.
        
        Args:
            target_date: Date to generate recap for
            
        Returns:
            List of recap dicts, one per project
        """
        target_date = target_date or date.today()
        
        async with self.pool.acquire() as conn:
            projects = await projects_repo.get_all(conn)
        
        recaps = []
        for project in projects:
            recap = await self.generate_daily_recap(
                project_id=project["id"],
                target_date=target_date,
            )
            recaps.append(recap)
        
        return recaps
    
    async def send_recap_to_management(
        self,
        recaps: list[dict[str, Any]],
        channels: list[str] | None = None,
    ) -> dict[str, bool]:
        """Send recap to management via configured channels.
        
        Args:
            recaps: List of recap dicts
            channels: List of channels to send to (slack, email)
            
        Returns:
            Dict with channel -> success status
        """
        channels = channels or ["slack"]
        
        # Build message
        message = self._format_recap_message(recaps)
        
        results = {}
        for channel in channels:
            if channel == "slack":
                results[channel] = await self._send_to_slack(message)
            elif channel == "email":
                results[channel] = await self._send_to_email(message)
        
        return results
    
    async def _generate_summary(
        self,
        date_str: str,
        project_name: str,
        completed: int,
        in_progress: int,
        blocked: int,
        task_details: str,
    ) -> str:
        """Generate summary using LLM."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"""Date: {date_str}
Project: {project_name}

Task Status:
- Completed: {completed}
- In Progress: {in_progress}
- Blocked: {blocked}

Recent Tasks:
{task_details}"""},
                ],
                max_tokens=self.max_tokens,
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            if content:
                result = __import__("json").loads(content)
                return result.get("details", "")
        except Exception as e:
            print(f"Recap generation error: {e}")
        
        # Fallback summary
        return self._fallback_summary(project_name, completed, in_progress, blocked)
    
    def _build_task_details(self, tasks: list[asyncpg.Record]) -> str:
        """Build task details string for context."""
        details = []
        for task in tasks[:10]:  # Limit to 10 most recent
            status_emoji = "✅" if task["status"] == "done" else "🔄" if task["status"] == "in_progress" else "⏳"
            deadline_str = f" (due: {task['deadline']})" if task.get("deadline") else ""
            details.append(f"{status_emoji} {task['description'][:50]}{'...' if len(task['description']) > 50 else ''}{deadline_str}")
        
        return "\n".join(details)
    
    def _fallback_summary(
        self,
        project_name: str,
        completed: int,
        in_progress: int,
        blocked: int,
    ) -> str:
        """Generate fallback summary without LLM."""
        total = completed + in_progress + blocked
        if total == 0:
            return f"No task activity in {project_name} today."
        
        parts = []
        if completed > 0:
            parts.append(f"{completed} completed")
        if in_progress > 0:
            parts.append(f"{in_progress} in progress")
        if blocked > 0:
            parts.append(f"{blocked} blocked")
        
        return f"{project_name}: {', '.join(parts)} today."
    
    async def _send_to_slack(self, message: str) -> bool:
        """Send recap to Slack."""
        import httpx
        from services.hermes.core.settings import get_settings
        
        settings = get_settings()
        token = settings.slack_bot_token
        
        if not token:
            print("Slack bot token not configured")
            return False
        
        # TODO: Get management channel from settings
        channel = "#management"  # Default
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {token.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "channel": channel,
                        "text": message,
                    },
                )
                result = response.json()
                return result.get("ok", False)
        except Exception as e:
            print(f"Slack send failed: {e}")
            return False
    
    async def _send_to_email(self, message: str) -> bool:
        """Send recap via email (placeholder)."""
        # TODO: Implement email sending
        print(f"Email recap: {message}")
        return True
    
    def _format_recap_message(self, recaps: list[dict[str, Any]]) -> str:
        """Format recaps for sending."""
        lines = ["📊 *Daily Project Recap*\n"]
        
        for recap in recaps:
            lines.append(f"*{recap['project']}* ({recap['date']})")
            lines.append(f"  ✅ Completed: {recap['completed']}")
            lines.append(f"  🔄 In Progress: {recap['in_progress']}")
            lines.append(f"  ⛔ Blocked: {recap['blocked']}")
            lines.append(f"  {recap['details']}")
            lines.append("")
        
        return "\n".join(lines)


def create_recap_agent(pool: asyncpg.Pool) -> RecapAgent:
    """Factory function to create RecapAgent."""
    return RecapAgent(pool)