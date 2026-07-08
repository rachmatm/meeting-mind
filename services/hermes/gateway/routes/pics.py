"""PIC API routes per blueprint section 10."""

from __future__ import annotations

import uuid
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from services.hermes.gateway.schemas import (
    PICContactCreate,
    PICContactResponse,
    PICCreate,
    PICDetailResponse,
    PICResponse,
)
from services.hermes.repositories import pics as pics_repo


def get_pool(request: Request) -> asyncpg.Pool:
    """Get DB pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool


router = APIRouter(prefix="/pics", tags=["pics"])


@router.post("", response_model=PICResponse, status_code=status.HTTP_201_CREATED)
async def create_pic(
    data: PICCreate,
    pool: asyncpg.Pool = Depends(get_pool),
) -> PICResponse:
    """Create a new PIC (Person-In-Charge)."""
    async with pool.acquire() as conn:
        pic = await pics_repo.create(
            conn,
            user_id=data.user_id,
            name=data.name,
            type=data.type,
            email=data.email,
            slack_id=data.slack_id,
            divisions=data.divisions,
            responsibilities=data.responsibilities,
            skills=data.skills,
            max_concurrent_tasks=data.max_concurrent_tasks,
            manager_id=data.manager_id,
        )
    return PICResponse(**dict(pic))


@router.get("", response_model=list[PICResponse])
async def list_pics(pool: asyncpg.Pool = Depends(get_pool)) -> list[PICResponse]:
    """List all active PICs."""
    async with pool.acquire() as conn:
        pic_list = await pics_repo.get_all(conn)
    return [PICResponse(**dict(p)) for p in pic_list]


@router.get("/available", response_model=list[PICResponse])
async def get_available_pics(
    division: str | None = None,
    responsibility: str | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[PICResponse]:
    """Get available PICs filtered by division/responsibility."""
    async with pool.acquire() as conn:
        pic_list = await pics_repo.get_available(conn, division=division, responsibility=responsibility)
    return [PICResponse(**dict(p)) for p in pic_list]


@router.get("/{pic_id}", response_model=PICDetailResponse)
async def get_pic(
    pic_id: Annotated[uuid.UUID, Path(description="PIC UUID")],
    pool: asyncpg.Pool = Depends(get_pool),
) -> PICDetailResponse:
    """Get PIC details with contacts."""
    async with pool.acquire() as conn:
        pic = await pics_repo.get_by_id(conn, pic_id)
        if not pic:
            raise HTTPException(status_code=404, detail="PIC not found")
        
        contacts = await pics_repo.get_contacts(conn, pic_id)
    
    return PICDetailResponse(
        **dict(pic),
        contacts=[PICContactResponse(**dict(c)) for c in contacts],
    )


@router.put("/{pic_id}", response_model=PICResponse)
async def update_pic(
    pic_id: uuid.UUID,
    data: PICCreate,
    pool: asyncpg.Pool = Depends(get_pool),
) -> PICResponse:
    """Update PIC info."""
    async with pool.acquire() as conn:
        pic = await pics_repo.update(
            conn,
            pic_id,
            name=data.name,
            email=data.email,
            slack_id=data.slack_id,
            divisions=data.divisions,
            responsibilities=data.responsibilities,
            skills=data.skills,
            max_concurrent_tasks=data.max_concurrent_tasks,
            manager_id=data.manager_id,
        )
        if not pic:
            raise HTTPException(status_code=404, detail="PIC not found")
    return PICResponse(**dict(pic))


@router.delete("/{pic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_pic(
    pic_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> None:
    """Deactivate PIC (soft delete)."""
    async with pool.acquire() as conn:
        success = await pics_repo.deactivate(conn, pic_id)
        if not success:
            raise HTTPException(status_code=404, detail="PIC not found")


# --- PIC Contacts ---

@router.post("/{pic_id}/contacts", response_model=PICContactResponse, status_code=status.HTTP_201_CREATED)
async def add_contact(
    pic_id: uuid.UUID,
    data: PICContactCreate,
    pool: asyncpg.Pool = Depends(get_pool),
) -> PICContactResponse:
    """Add contact for a PIC."""
    async with pool.acquire() as conn:
        pic = await pics_repo.get_by_id(conn, pic_id)
        if not pic:
            raise HTTPException(status_code=404, detail="PIC not found")
        
        contact = await pics_repo.add_contact(
            conn,
            pic_id,
            contact_type=data.contact_type,
            contact_value=data.contact_value,
            person_name=data.person_name,
            is_primary=data.is_primary,
        )
    return PICContactResponse(**dict(contact))


@router.get("/{pic_id}/contacts", response_model=list[PICContactResponse])
async def list_contacts(
    pic_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[PICContactResponse]:
    """List PIC contacts."""
    async with pool.acquire() as conn:
        contacts = await pics_repo.get_contacts(conn, pic_id)
    return [PICContactResponse(**dict(c)) for c in contacts]


@router.delete("/{pic_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    pic_id: uuid.UUID,
    contact_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> None:
    """Remove contact."""
    async with pool.acquire() as conn:
        success = await pics_repo.delete_contact(conn, contact_id)
        if not success:
            raise HTTPException(status_code=404, detail="Contact not found")