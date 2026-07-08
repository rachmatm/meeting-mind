"""Meeting API routes per blueprint section 10."""

from __future__ import annotations

import uuid
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from services.hermes.gateway.schemas import (
    MeetingCreate,
    MeetingResponse,
    MeetingUpdate,
)
from services.hermes.repositories import meetings as meetings_repo


def get_pool(request: Request) -> asyncpg.Pool:
    """Get DB pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool


router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    data: MeetingCreate,
    pool: asyncpg.Pool = Depends(get_pool),
) -> MeetingResponse:
    """Create a new meeting record (typically after transcription)."""
    async with pool.acquire() as conn:
        meeting = await meetings_repo.create(
            conn,
            transcript=data.transcript,
            project_id=data.project_id,
            title=data.title,
            audio_url=data.audio_url,
        )
    return MeetingResponse(**dict(meeting))


@router.get("", response_model=list[MeetingResponse])
async def list_meetings(
    project_id: uuid.UUID | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[MeetingResponse]:
    """List meetings, optionally filtered by project."""
    async with pool.acquire() as conn:
        meeting_list = await meetings_repo.get_all(conn, project_id=project_id)
    return [MeetingResponse(**dict(m)) for m in meeting_list]


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: Annotated[uuid.UUID, Path(description="Meeting UUID")],
    pool: asyncpg.Pool = Depends(get_pool),
) -> MeetingResponse:
    """Get meeting details."""
    async with pool.acquire() as conn:
        meeting = await meetings_repo.get_by_id(conn, meeting_id)
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
    return MeetingResponse(**dict(meeting))


@router.put("/{meeting_id}", response_model=MeetingResponse)
async def update_meeting(
    meeting_id: uuid.UUID,
    data: MeetingUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
) -> MeetingResponse:
    """Update meeting (approve, add summary, etc.)."""
    async with pool.acquire() as conn:
        meeting = await meetings_repo.update(
            conn,
            meeting_id,
            project_id=data.project_id,
            title=data.title,
            transcript=data.transcript,
            summary=data.summary,
            audio_url=data.audio_url,
            status=data.status,
        )
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
    return MeetingResponse(**dict(meeting))


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> None:
    """Delete meeting."""
    async with pool.acquire() as conn:
        success = await meetings_repo.delete(conn, meeting_id)
        if not success:
            raise HTTPException(status_code=404, detail="Meeting not found")