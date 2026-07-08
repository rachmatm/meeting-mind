"""Tasks repository.

CRUD per blueprint section 10.
"""

from __future__ import annotations

import uuid
from datetime import date

import asyncpg


async def create(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    division: str,
    description: str,
    pic_id: uuid.UUID | None = None,
    deadline: date | None = None,
    meeting_id: uuid.UUID | None = None,
    status: str = "todo",
) -> asyncpg.Record:
    """Create a new task."""
    return await conn.fetchrow(
        """
        INSERT INTO tasks (project_id, division, description, pic_id, deadline, meeting_id, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *;
        """,
        project_id, division, description, pic_id, deadline, meeting_id, status,
    )


async def get_by_id(conn: asyncpg.Connection, task_id: uuid.UUID) -> asyncpg.Record | None:
    """Get task by ID."""
    return await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)


async def get_by_project(conn: asyncpg.Connection, project_id: uuid.UUID) -> list[asyncpg.Record]:
    """Get all tasks for a project."""
    return await conn.fetch(
        "SELECT * FROM tasks WHERE project_id = $1 ORDER BY deadline ASC, created_at DESC",
        project_id,
    )


async def get_by_pic(conn: asyncpg.Connection, pic_id: uuid.UUID) -> list[asyncpg.Record]:
    """Get all tasks assigned to a PIC."""
    return await conn.fetch(
        "SELECT * FROM tasks WHERE pic_id = $1 ORDER BY deadline ASC, created_at DESC",
        pic_id,
    )


async def get_by_status(conn: asyncpg.Connection, status: str) -> list[asyncpg.Record]:
    """Get tasks by status."""
    return await conn.fetch(
        "SELECT t.*, p.name as project_name FROM tasks t JOIN projects p ON t.project_id = p.id WHERE t.status = $1 ORDER BY t.deadline ASC",
        status,
    )


async def get_due_soon(conn: asyncpg.Connection, days: int = 1) -> list[asyncpg.Record]:
    """Get tasks due within N days."""
    return await conn.fetch(
        """
        SELECT t.*, p.name as project_name, pic.name as pic_name
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        LEFT JOIN pics pic ON t.pic_id = pic.id
        WHERE t.status != 'done' 
          AND t.deadline IS NOT NULL 
          AND t.deadline <= CURRENT_DATE + $1
        ORDER BY t.deadline ASC
        """,
        days,
    )


async def update(
    conn: asyncpg.Connection,
    task_id: uuid.UUID,
    *,
    division: str | None = None,
    description: str | None = None,
    pic_id: uuid.UUID | None = None,
    deadline: date | None = None,
    status: str | None = None,
) -> asyncpg.Record | None:
    """Update task details."""
    fields: list[str] = []
    values: list = []
    param_num = 1
    
    if division is not None:
        fields.append(f"division = ${param_num}")
        values.append(division)
        param_num += 1
    if description is not None:
        fields.append(f"description = ${param_num}")
        values.append(description)
        param_num += 1
    if pic_id is not None:
        fields.append(f"pic_id = ${param_num}")
        values.append(pic_id)
        param_num += 1
    if deadline is not None:
        fields.append(f"deadline = ${param_num}")
        values.append(deadline)
        param_num += 1
    if status is not None:
        fields.append(f"status = ${param_num}")
        values.append(status)
        param_num += 1
    
    if not fields:
        return await get_by_id(conn, task_id)
    
    fields.append("updated_at = NOW()")
    values.append(task_id)
    
    query = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ${param_num} RETURNING *"
    return await conn.fetchrow(query, *values)


async def delete(conn: asyncpg.Connection, task_id: uuid.UUID) -> bool:
    """Delete task."""
    result = await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
    return result != "DELETE 0"


async def assign_pic(conn: asyncpg.Connection, task_id: uuid.UUID, pic_id: uuid.UUID) -> asyncpg.Record | None:
    """Assign PIC to task."""
    return await conn.fetchrow(
        "UPDATE tasks SET pic_id = $2, updated_at = NOW() WHERE id = $1 RETURNING *",
        task_id, pic_id,
    )