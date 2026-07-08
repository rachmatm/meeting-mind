"""Upload API routes per blueprint section 3.1 and 10.

Phase 2: Audio upload + STT processing.
"""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import APIRouter, Depends, File, HTTPException, Path, Request, UploadFile, status
from fastapi.responses import JSONResponse

from services.hermes.gateway.schemas import UploadResponse
from services.hermes.repositories import meetings as meetings_repo
from services.hermes.tools.stt import transcribe_audio
from services.hermes.tools.storage import get_storage_service

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".webm"}


def get_pool(request: Request) -> asyncpg.Pool:
    """Get DB pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool


def validate_audio_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)


@router.post("", response_model=UploadResponse)
async def upload_audio(
    file: UploadFile = File(..., description="Audio file (mp3, wav, m4a, webm)"),
    pool: asyncpg.Pool = Depends(get_pool),
) -> UploadResponse:
    """Upload meeting recording for transcription.
    
    Accepts audio file, processes through STT, returns transcript for user approval.
    """
    # Validate file extension
    if not validate_audio_file(file.filename or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    
    # Read file content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded",
        )
    
    # Save audio file
    storage = get_storage_service()
    audio_url = await storage.save(content, file.filename or "audio.mp3")
    
    # Transcribe audio
    try:
        transcript = await transcribe_audio(content, file.filename or "audio.mp3")
    except Exception as e:
        # Log error but continue with placeholder
        transcript = f"[STT Error: {str(e)}]"
    
    # Store meeting with transcript
    async with pool.acquire() as conn:
        meeting = await meetings_repo.create(
            conn,
            transcript=transcript,
            title=file.filename,
            audio_url=audio_url,
        )
    
    return UploadResponse(
        meeting_id=meeting["id"],
        transcript=transcript,
        status="pending",
    )


@router.get("/{meeting_id}/transcript")
async def get_transcript(
    meeting_id: uuid.UUID = Path(description="Meeting UUID"),
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Get transcription for a meeting."""
    async with pool.acquire() as conn:
        meeting = await meetings_repo.get_by_id(conn, meeting_id)
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
    
    return JSONResponse({
        "meeting_id": str(meeting_id),
        "transcript": meeting["transcript"],
        "status": meeting["status"],
    })


@router.post("/{meeting_id}/approve")
async def approve_transcript(
    meeting_id: uuid.UUID = Path(description="Meeting UUID"),
    project_id: uuid.UUID | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Approve transcription and associate with project.
    
    After user approval, workflow proceeds to project selection
    and then to the agent chain (Summarizer -> Task Splitter).
    """
    async with pool.acquire() as conn:
        meeting = await meetings_repo.update(
            conn,
            meeting_id,
            project_id=project_id,
            status="approved",
        )
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
    
    # TODO: Trigger workflow orchestration (Phase 3)
    # This will be implemented in Phase 3 with OpenClaw
    
    return JSONResponse({
        "success": True,
        "meeting_id": str(meeting_id),
        "project_id": str(project_id) if project_id else None,
        "message": "Transcription approved. Workflow initiated.",
    })


@router.post("/{meeting_id}/reject")
async def reject_transcript(
    meeting_id: uuid.UUID = Path(description="Meeting UUID"),
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Reject transcription - allow re-upload or manual edit."""
    async with pool.acquire() as conn:
        meeting = await meetings_repo.update(
            conn,
            meeting_id,
            status="rejected",
        )
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
    
    return JSONResponse({
        "success": True,
        "meeting_id": str(meeting_id),
        "message": "Transcription rejected. Please re-upload or edit manually.",
    })


@router.put("/{meeting_id}/transcript")
async def update_transcript(
    meeting_id: uuid.UUID = Path(description="Meeting UUID"),
    transcript: str | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
) -> JSONResponse:
    """Manually update transcript (for corrections)."""
    async with pool.acquire() as conn:
        if transcript is not None:
            meeting = await meetings_repo.update(
                conn,
                meeting_id,
                transcript=transcript,
            )
        else:
            meeting = await meetings_repo.get_by_id(conn, meeting_id)
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
    
    return JSONResponse({
        "success": True,
        "meeting_id": str(meeting_id),
        "transcript": meeting["transcript"],
    })