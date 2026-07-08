"""Task Splitter Agent - splits summary into actionable tasks with PIC assignment.

Blueprint section 6.2 - Input: Summary, Output: [{divisi, task, deadline, pic_id}]
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

import asyncpg

from openai import AsyncOpenAI

from services.hermes.core.settings import get_settings
from services.hermes.repositories import pics as pics_repo
from services.hermes.repositories import projects as projects_repo


# Output schema per blueprint section 6.2
TASK_SPLITTER_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "divisi": {"type": "string"},
                    "task": {"type": "string"},
                    "deadline": {"type": "string"},  # YYYY-MM-DD or null
                    "pic_id": {"type": "string"},  # UUID or null
                },
                "required": ["divisi", "task"],
            },
        }
    },
    "required": ["tasks"],
}


SYSTEM_PROMPT = """You are a task splitter assistant. Your job is to break down meeting summaries into actionable tasks.

Instructions:
1. Analyze the meeting summary and key points
2. Create specific, actionable tasks for each item
3. Assign a division/team (divisi) to each task
4. Suggest a reasonable deadline (YYYY-MM-DD format, or null if not urgent)
5. For PIC assignment, use the format "uuid" if you have a specific person in mind, otherwise null

Divisions available: engineering, design, marketing, product, operations, sales, support

Output Format: JSON with the following structure:
{
  "tasks": [
    {
      "divisi": "engineering",
      "task": "Implement user authentication",
      "deadline": "2026-07-15",
      "pic_id": null
    }
  ]
}

Constraint: Output must be valid JSON only."""


class TaskSplitterAgent:
    """Agent for splitting summaries into tasks."""
    
    def __init__(self, pool: asyncpg.Pool):
        settings = get_settings()
        self.pool = pool
        self.client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
        )
        self.model = settings.llm_model
        self.max_tokens = settings.llm_max_tokens * 3
    
    async def split_tasks(self, summary: dict, project_id: uuid.UUID) -> list[dict]:
        """Split meeting summary into actionable tasks.
        
        Args:
            summary: Dict with summary, key_points, action_items
            project_id: Project ID for PIC lookup
            
        Returns:
            List of task dicts with divisi, task, deadline, pic_id
        """
        # Get available PICs for this project
        project_pics = await self._get_project_pics(project_id)
        
        # Build context for the LLM
        context = self._build_context(summary, project_pics)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": context},
                ],
                max_tokens=self.max_tokens,
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            if content:
                result = json.loads(content)
                tasks = self._validate_tasks(result.get("tasks", []))
                
                # Assign PICs based on division
                for task in tasks:
                    if task.get("pic_id") is None:
                        task["pic_id"] = await self._suggest_pic(task["divisi"], project_pics)
                
                return tasks
            
        except Exception as e:
            print(f"TaskSplitter error: {e}")
        
        # Fallback
        return self._fallback_tasks(summary)
    
    async def _get_project_pics(self, project_id: uuid.UUID) -> list[asyncpg.Record]:
        """Get PICs assigned to a project."""
        async with self.pool.acquire() as conn:
            return await projects_repo.get_project_pics(conn, project_id)
    
    def _build_context(self, summary: dict, project_pics: list[asyncpg.Record]) -> str:
        """Build context string with summary and available PICs."""
        pic_info = "\n".join([
            f"- {p['name']} ({p.get('divisions', [])}), responsibilities: {p.get('responsibilities', [])}"
            for p in project_pics
        ])
        
        return f"""Meeting Summary:
{summary.get('summary', '')}

Key Points:
{chr(10).join(f'- {p}' for p in summary.get('key_points', []))}

Action Items:
{chr(10).join(f'- {a}' for a in summary.get('action_items', []))}

Available Team Members (PICs):
{pic_info or 'No PICs assigned to this project yet'}"""
    
    async def _suggest_pic(self, division: str, project_pics: list[asyncpg.Record]) -> uuid.UUID | None:
        """Suggest best PIC for a task based on division."""
        # Filter by division
        matching = [p for p in project_pics if division.lower() in [d.lower() for d in p.get("divisions", [])]]
        
        if not matching:
            # Return first available PIC
            return project_pics[0]["id"] if project_pics else None
        
        # Return first matching
        return matching[0]["id"]
    
    def _validate_tasks(self, tasks: list) -> list[dict]:
        """Validate and normalize task list."""
        validated = []
        for t in tasks:
            task = {
                "divisi": t.get("divisi", "operations"),
                "task": t.get("task", ""),
                "deadline": t.get("deadline"),
                "pic_id": t.get("pic_id"),
            }
            
            # Validate deadline format
            if task["deadline"]:
                try:
                    # Ensure valid date
                    date.fromisoformat(task["deadline"])
                except (ValueError, TypeError):
                    task["deadline"] = (date.today() + timedelta(days=7)).isoformat()
            
            if task["task"]:  # Only add non-empty tasks
                validated.append(task)
        
        return validated
    
    def _fallback_tasks(self, summary: dict) -> list[dict]:
        """Generate fallback tasks when LLM unavailable."""
        tasks = []
        for action in summary.get("action_items", []):
            tasks.append({
                "divisi": "operations",
                "task": action,
                "deadline": (date.today() + timedelta(days=7)).isoformat(),
                "pic_id": None,
            })
        
        if not tasks:
            tasks.append({
                "divisi": "operations",
                "task": "Review meeting summary and create tasks",
                "deadline": (date.today() + timedelta(days=1)).isoformat(),
                "pic_id": None,
            })
        
        return tasks


def create_task_splitter(pool: asyncpg.Pool) -> TaskSplitterAgent:
    """Factory function to create TaskSplitterAgent."""
    return TaskSplitterAgent(pool)