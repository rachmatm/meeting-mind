"""PIC (Person-In-Charge) repository.

CRUD + availability lookup per blueprint section 10.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg


async def create(
    conn: asyncpg.Connection,
    *,
    user_id: str,
    name: str,
    type: str = "person",
    email: str | None = None,
    slack_id: str | None = None,
    divisions: list[str] | None = None,
    responsibilities: list[str] | None = None,
    skills: list[str] | None = None,
    max_concurrent_tasks: int = 5,
    manager_id: uuid.UUID | None = None,
) -> asyncpg.Record:
    """Create a new PIC."""
    return await conn.fetchrow(
        """
        INSERT INTO pics (user_id, name, type, email, slack_id, divisions, responsibilities, skills, max_concurrent_tasks, manager_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING *;
        """,
        user_id, name, type, email, slack_id, divisions, responsibilities, skills, max_concurrent_tasks, manager_id,
    )


async def get_by_id(conn: asyncpg.Connection, pic_id: uuid.UUID) -> asyncpg.Record | None:
    """Get PIC by ID."""
    return await conn.fetchrow("SELECT * FROM pics WHERE id = $1 AND is_active = true", pic_id)


async def get_all(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """List all active PICs."""
    return await conn.fetch("SELECT * FROM pics WHERE is_active = true ORDER BY name")


async def get_available(
    conn: asyncpg.Connection,
    *,
    division: str | None = None,
    responsibility: str | None = None,
) -> list[asyncpg.Record]:
    """Get available PICs filtered by division/responsibility."""
    query = """
        SELECT p.*, 
               (SELECT COUNT(*) FROM tasks t WHERE t.pic_id = p.id AND t.status != 'done') as current_tasks
        FROM pics p
        WHERE p.is_active = true
    """
    params: list[Any] = []
    
    if division:
        params.append(division)
        query += f" AND $${len(params)} = ANY(p.divisions)"
    
    if responsibility:
        params.append(responsibility)
        query += f" AND $${len(params)} = ANY(p.responsibilities)"
    
    query += " ORDER BY current_tasks ASC LIMIT 20"
    
    return await conn.fetch(query, *params)


async def update(
    conn: asyncpg.Connection,
    pic_id: uuid.UUID,
    *,
    name: str | None = None,
    email: str | None = None,
    slack_id: str | None = None,
    divisions: list[str] | None = None,
    responsibilities: list[str] | None = None,
    skills: list[str] | None = None,
    max_concurrent_tasks: int | None = None,
    manager_id: uuid.UUID | None = None,
) -> asyncpg.Record | None:
    """Update PIC details."""
    fields: list[str] = []
    values: list[Any] = []
    param_num = 1
    
    if name is not None:
        fields.append(f"name = ${param_num}")
        values.append(name)
        param_num += 1
    if email is not None:
        fields.append(f"email = ${param_num}")
        values.append(email)
        param_num += 1
    if slack_id is not None:
        fields.append(f"slack_id = ${param_num}")
        values.append(slack_id)
        param_num += 1
    if divisions is not None:
        fields.append(f"divisions = ${param_num}")
        values.append(divisions)
        param_num += 1
    if responsibilities is not None:
        fields.append(f"responsibilities = ${param_num}")
        values.append(responsibilities)
        param_num += 1
    if skills is not None:
        fields.append(f"skills = ${param_num}")
        values.append(skills)
        param_num += 1
    if max_concurrent_tasks is not None:
        fields.append(f"max_concurrent_tasks = ${param_num}")
        values.append(max_concurrent_tasks)
        param_num += 1
    if manager_id is not None:
        fields.append(f"manager_id = ${param_num}")
        values.append(manager_id)
        param_num += 1
    
    if not fields:
        return await get_by_id(conn, pic_id)
    
    fields.append("updated_at = NOW()")
    values.append(pic_id)
    
    query = f"UPDATE pics SET {', '.join(fields)} WHERE id = ${param_num} RETURNING *"
    return await conn.fetchrow(query, *values)


async def deactivate(conn: asyncpg.Connection, pic_id: uuid.UUID) -> bool:
    """Soft delete - set is_active = false."""
    result = await conn.execute(
        "UPDATE pics SET is_active = false, updated_at = NOW() WHERE id = $1",
        pic_id,
    )
    return result != "UPDATE 0"


# --- PIC Contacts ---

async def add_contact(
    conn: asyncpg.Connection,
    pic_id: uuid.UUID,
    *,
    contact_type: str,
    contact_value: str,
    person_name: str,
    is_primary: bool = False,
) -> asyncpg.Record:
    """Add contact method for a PIC."""
    return await conn.fetchrow(
        """
        INSERT INTO pic_contacts (pic_id, contact_type, contact_value, person_name, is_primary)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *;
        """,
        pic_id, contact_type, contact_value, person_name, is_primary,
    )


async def get_contacts(conn: asyncpg.Connection, pic_id: uuid.UUID) -> list[asyncpg.Record]:
    """Get all contacts for a PIC."""
    return await conn.fetch(
        "SELECT * FROM pic_contacts WHERE pic_id = $1 ORDER BY is_primary DESC, created_at",
        pic_id,
    )


async def delete_contact(conn: asyncpg.Connection, contact_id: uuid.UUID) -> bool:
    """Delete a contact."""
    result = await conn.execute("DELETE FROM pic_contacts WHERE id = $1", contact_id)
    return result != "DELETE 0"