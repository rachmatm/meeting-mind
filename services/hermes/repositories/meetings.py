"""Meetings repository.

CRUD per blueprint section 10.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg


async def create(
    conn: asyncpg.Connection,
    *,
    transcript: str,
    project_id: uuid.UUID | None = None,
    title: str | None = None,
    audio_url: str | None = None,
) -> asyncpg.Record:
    """Create a new meeting record."""
    return await conn.fetchrow(
        """
        INSERT INTO meetings (transcript, project_id, title, audio_url)
        VALUES ($1, $2, $3, $4)
        RETURNING *;
        """,
        transcript, project_id, title, audio_url,
    )


async def get_by_id(conn: asyncpg.Connection, meeting_id: uuid.UUID) -> asyncpg.Record | None:
    """Get meeting by ID."""
    return await conn.fetchrow("SELECT * FROM meetings WHERE id = $1", meeting_id)


async def get_all(conn: asyncpg.Connection, project_id: uuid.UUID | None = None) -> list[asyncpg.Record]:
    """List meetings, optionally filtered by project."""
    if project_id:
        return await conn.fetch(
            "SELECT * FROM meetings WHERE project_id = $1 ORDER BY created_at DESC",
            project_id,
        )
    return await conn.fetch("SELECT * FROM meetings ORDER BY created_at DESC")


async def update(
    conn: asyncpg.Connection,
    meeting_id: uuid.UUID,
    *,
    project_id: uuid.UUID | None = None,
    title: str | None = None,
    transcript: str | None = None,
    summary: dict[str, Any] | None = None,
    audio_url: str | None = None,
    status: str | None = None,
) -> asyncpg.Record | None:
    """Update meeting details."""
    fields: list[str] = []
    values: list[Any] = []
    param_num = 1
    
    if project_id is not None:
        fields.append(f"project_id = ${param_num}")
        values.append(project_id)
        param_num += 1
    if title is not None:
        fields.append(f"title = ${param_num}")
        values.append(title)
        param_num += 1
    if transcript is not None:
        fields.append(f"transcript = ${param_num}")
        values.append(transcript)
        param_num += 1
    if summary is not None:
        fields.append(f"summary = ${param_num}")
        values.append(summary)
        param_num += 1
    if audio_url is not None:
        fields.append(f"audio_url = ${param_num}")
        values.append(audio_url)
        param_num += 1
    if status is not None:
        fields.append(f"status = ${param_num}")
        values.append(status)
        param_num += 1
    
    if not fields:
        return await get_by_id(conn, meeting_id)
    
    fields.append("updated_at = NOW()")
    values.append(meeting_id)
    
    query = f"UPDATE meetings SET {', '.join(fields)} WHERE id = ${param_num} RETURNING *"
    return await conn.fetchrow(query, *values)


async def delete(conn: asyncpg.Connection, meeting_id: uuid.UUID) -> bool:
    """Delete meeting."""
    result = await conn.execute("DELETE FROM meetings WHERE id = $1", meeting_id)
    return result != "DELETE 0"