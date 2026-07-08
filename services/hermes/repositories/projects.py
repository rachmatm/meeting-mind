"""Project repository.

CRUD + PIC associations per blueprint section 10.
"""

from __future__ import annotations

import uuid

import asyncpg


async def create(
    conn: asyncpg.Connection,
    *,
    name: str,
    description: str | None = None,
    notion_page_id: str | None = None,
) -> asyncpg.Record:
    """Create a new project."""
    return await conn.fetchrow(
        """
        INSERT INTO projects (name, description, notion_page_id)
        VALUES ($1, $2, $3)
        RETURNING *;
        """,
        name, description, notion_page_id,
    )


async def get_by_id(conn: asyncpg.Connection, project_id: uuid.UUID) -> asyncpg.Record | None:
    """Get project by ID."""
    return await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)


async def get_all(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """List all projects."""
    return await conn.fetch("SELECT * FROM projects ORDER BY created_at DESC")


async def get_with_pics(conn: asyncpg.Connection, project_id: uuid.UUID) -> dict | None:
    """Get project with its PICs."""
    project = await get_by_id(conn, project_id)
    if not project:
        return None
    
    pics = await conn.fetch(
        """
        SELECT p.*, pp.role, pp.joined_at
        FROM pics p
        JOIN project_pics pp ON p.id = pp.pic_id
        WHERE pp.project_id = $1 AND p.is_active = true
        ORDER BY pp.role DESC, p.name
        """,
        project_id,
    )
    
    return {
        "id": project["id"],
        "name": project["name"],
        "description": project["description"],
        "notion_page_id": project["notion_page_id"],
        "created_at": project["created_at"],
        "pics": [dict(p) for p in pics],
    }


async def update(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    notion_page_id: str | None = None,
) -> asyncpg.Record | None:
    """Update project."""
    fields: list[str] = []
    values: list = []
    param_num = 1
    
    if name is not None:
        fields.append(f"name = ${param_num}")
        values.append(name)
        param_num += 1
    if description is not None:
        fields.append(f"description = ${param_num}")
        values.append(description)
        param_num += 1
    if notion_page_id is not None:
        fields.append(f"notion_page_id = ${param_num}")
        values.append(notion_page_id)
        param_num += 1
    
    if not fields:
        return await get_by_id(conn, project_id)
    
    values.append(project_id)
    query = f"UPDATE projects SET {', '.join(fields)} WHERE id = ${param_num} RETURNING *"
    return await conn.fetchrow(query, *values)


async def delete(conn: asyncpg.Connection, project_id: uuid.UUID) -> bool:
    """Delete project (cascades to project_pics)."""
    result = await conn.execute("DELETE FROM projects WHERE id = $1", project_id)
    return result != "DELETE 0"


# --- Project-PIC associations ---

async def add_pic(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    pic_id: uuid.UUID,
    role: str = "member",
) -> asyncpg.Record:
    """Add PIC to project."""
    return await conn.fetchrow(
        """
        INSERT INTO project_pics (project_id, pic_id, role)
        VALUES ($1, $2, $3)
        ON CONFLICT (project_id, pic_id) DO UPDATE SET role = $3
        RETURNING *;
        """,
        project_id, pic_id, role,
    )


async def remove_pic(conn: asyncpg.Connection, project_id: uuid.UUID, pic_id: uuid.UUID) -> bool:
    """Remove PIC from project."""
    result = await conn.execute(
        "DELETE FROM project_pics WHERE project_id = $1 AND pic_id = $2",
        project_id, pic_id,
    )
    return result != "DELETE 0"


async def get_project_pics(conn: asyncpg.Connection, project_id: uuid.UUID) -> list[asyncpg.Record]:
    """Get all PICs for a project."""
    return await conn.fetch(
        """
        SELECT p.*, pp.role, pp.joined_at
        FROM pics p
        JOIN project_pics pp ON p.id = pp.pic_id
        WHERE pp.project_id = $1 AND p.is_active = true
        ORDER BY pp.role DESC, p.name
        """,
        project_id,
    )