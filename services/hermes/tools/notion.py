"""Notion API client for page creation and kanban boards.

Blueprint section 9 - Create pages with meeting summaries and kanban boards.
"""

from __future__ import annotations

from typing import Any

from services.hermes.core.settings import get_settings


class NotionClient:
    """Notion API client for creating pages and databases."""
    
    BASE_URL = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"
    
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.notion_api_key
        self.database_id = settings.notion_database_id
        self._session = None
    
    async def _get_headers(self) -> dict[str, str]:
        """Get headers for Notion API requests."""
        return {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "Notion-Version": self.API_VERSION,
        }
    
    async def create_page(
        self,
        title: str,
        content: str | None = None,
        parent_database_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new page in Notion.
        
        Args:
            title: Page title
            content: Optional content to add to the page
            parent_database_id: Parent database ID (if creating under a database)
            
        Returns:
            Created page data from Notion API
        """
        import httpx
        
        parent_id = parent_database_id or self.database_id
        
        # Build children blocks for content
        children = []
        if content:
            # Split content into paragraphs (max 2000 chars per block)
            for i in range(0, len(content), 2000):
                chunk = content[i:i + 2000]
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}]
                    }
                })
        
        # Build page payload
        payload = {
            "parent": {"database_id": parent_id} if parent_id else {"page_id": "root"},
            "properties": {
                "Name": {
                    "title": [{"type": "text", "text": {"content": title}}]
                }
            }
        }
        
        # Add children if we have content
        if children:
            payload["children"] = children
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/pages",
                headers=await self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    
    async def create_kanban_database(
        self,
        parent_page_id: str,
        database_name: str = "Tasks",
    ) -> dict[str, Any]:
        """Create a child database for kanban board.
        
        Args:
            parent_page_id: Parent page to create database under
            database_name: Name for the tasks database
            
        Returns:
            Created database with properties for kanban
        """
        import httpx
        
        # Define kanban properties per blueprint section 9.2
        payload = {
            "parent": {"page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": database_name}}],
            "properties": {
                "Task": {"title": {}},
                "Division": {
                    "select": {}
                },
                "PIC": {
                    "people": {}
                },
                "Deadline": {
                    "date": {}
                },
                "Status": {
                    "select": {
                        "options": [
                            {"name": "To Do", "color": "red"},
                            {"name": "In Progress", "color": "yellow"},
                            {"name": "Done", "color": "green"},
                        ]
                    }
                }
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/databases",
                headers=await self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    
    async def create_task_in_database(
        self,
        database_id: str,
        task_title: str,
        division: str | None = None,
        pic_id: str | None = None,
        deadline: str | None = None,
        status: str = "To Do",
    ) -> dict[str, Any]:
        """Create a task entry in the kanban database.
        
        Args:
            database_id: Database ID to add task to
            task_title: Task title/description
            division: Division/team (select)
            pic_id: PIC person ID (people)
            deadline: Deadline date (YYYY-MM-DD)
            status: Status (To Do, In Progress, Done)
            
        Returns:
            Created task page
        """
        import httpx
        
        properties = {
            "Task": {
                "title": [{"type": "text", "text": {"content": task_title}}]
            },
            "Status": {
                "select": {"name": status}
            }
        }
        
        if division:
            properties["Division"] = {"select": {"name": division}}
        
        if pic_id:
            properties["PIC"] = {"people": [{"id": pic_id}]}
        
        if deadline:
            properties["Deadline"] = {"date": {"start": deadline}}
        
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/pages",
                headers=await self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    
    async def create_meeting_page_with_kanban(
        self,
        project_name: str,
        meeting_summary: dict[str, Any],
        tasks: list[dict[str, Any]],
        parent_page_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a complete meeting page with summary and kanban.
        
        Args:
            project_name: Project name for the page
            meeting_summary: Dict with summary, key_points, action_items
            tasks: List of task dicts to add to kanban
            parent_page_id: Optional parent page ID
            
        Returns:
            Created page with kanban database
        """
        import httpx
        
        # Build content blocks from meeting summary
        children = []
        
        # Summary section
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Summary"}}]
            }
        })
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": meeting_summary.get("summary", "")}}]
            }
        })
        
        # Key Points
        if meeting_summary.get("key_points"):
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Key Points"}}]
                }
            })
            for point in meeting_summary["key_points"]:
                children.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": point}}]
                    }
                })
        
        # Action Items
        if meeting_summary.get("action_items"):
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Action Items"}}]
                }
            })
            for item in meeting_summary["action_items"]:
                children.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": item}}]
                    }
                })
        
        # Create page with content
        page_payload = {
            "parent": {"page_id": parent_page_id} if parent_page_id else {"page_id": "root"},
            "properties": {
                "Name": {
                    "title": [{"type": "text", "text": {"content": f"Meeting: {project_name}"}}]
                }
            },
            "children": children[:100]  # Notion API limit
        }
        
        async with httpx.AsyncClient() as client:
            # Create the page
            page_response = await client.post(
                f"{self.BASE_URL}/pages",
                headers=await self._get_headers(),
                json=page_payload,
            )
            page_response.raise_for_status()
            page_data = page_response.json()
            page_id = page_data["id"]
            
            # Create kanban database as child
            kanban_response = await self.create_kanban_database(page_id, "Tasks")
            kanban_id = kanban_response["id"]
            
            # Add tasks to kanban
            tasks_created = 0
            for task in tasks:
                try:
                    await self.create_task_in_database(
                        kanban_id,
                        task.get("description", task.get("task", "")),
                        division=task.get("divisi"),
                        pic_id=task.get("pic_id"),
                        deadline=task.get("deadline"),
                        status="To Do",
                    )
                    tasks_created += 1
                except Exception as e:
                    print(f"Failed to create task in Notion: {e}")
            
            return {
                "page_id": page_id,
                "page_url": page_data["url"],
                "kanban_database_id": kanban_id,
                "tasks_created": tasks_created,
            }


# Singleton instance
_notion_client: NotionClient | None = None


def get_notion_client() -> NotionClient:
    """Get or create Notion client singleton."""
    global _notion_client
    if _notion_client is None:
        _notion_client = NotionClient()
    return _notion_client


async def create_meeting_page(
    project_name: str,
    meeting_summary: dict[str, Any],
    tasks: list[dict[str, Any]],
    parent_page_id: str | None = None,
) -> dict[str, Any]:
    """Convenience function to create meeting page with kanban."""
    client = get_notion_client()
    return await client.create_meeting_page_with_kanban(
        project_name,
        meeting_summary,
        tasks,
        parent_page_id,
    )