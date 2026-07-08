"""Project API routes per blueprint section 10."""

from __future__ import annotations

import uuid
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from services.hermes.gateway.schemas import (
    ProjectCreate,
    ProjectDetailResponse,
    ProjectPICAdd,
    ProjectResponse,
)
from services.hermes.repositories import projects as projects_repo
from services.hermes.repositories import pics as pics_repo


def get_pool(request: Request) -> asyncpg.Pool:
    """Get DB pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool


router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    pool: asyncpg.Pool = Depends(get_pool),
) -> ProjectResponse:
    """Create a new project."""
    async with pool.acquire() as conn:
        project = await projects_repo.create(
            conn,
            name=data.name,
            description=data.description,
            notion_page_id=data.notion_page_id,
        )
    return ProjectResponse(**dict(project))


@router.get("", response_model=list[ProjectResponse])
async def list_projects(pool: asyncpg.Pool = Depends(get_pool)) -> list[ProjectResponse]:
    """List all projects."""
    async with pool.acquire() as conn:
        project_list = await projects_repo.get_all(conn)
    return [ProjectResponse(**dict(p)) for p in project_list]


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: Annotated[uuid.UUID, Path(description="Project UUID")],
    pool: asyncpg.Pool = Depends(get_pool),
) -> ProjectDetailResponse:
    """Get project with PICs."""
    async with pool.acquire() as conn:
        project = await projects_repo.get_with_pics(conn, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDetailResponse(**project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectCreate,
    pool: asyncpg.Pool = Depends(get_pool),
) -> ProjectResponse:
    """Update project."""
    async with pool.acquire() as conn:
        project = await projects_repo.update(
            conn,
            project_id,
            name=data.name,
            description=data.description,
            notion_page_id=data.notion_page_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse(**dict(project))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> None:
    """Delete project."""
    async with pool.acquire() as conn:
        success = await projects_repo.delete(conn, project_id)
        if not success:
            raise HTTPException(status_code=404, detail="Project not found")


# --- Project-PIC associations ---

@router.post("/{project_id}/pics", status_code=status.HTTP_201_CREATED)
async def add_pic_to_project(
    project_id: uuid.UUID,
    data: ProjectPICAdd,
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Add PIC to project."""
    async with pool.acquire() as conn:
        # Verify project exists
        project = await projects_repo.get_by_id(conn, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Verify PIC exists
        pic = await pics_repo.get_by_id(conn, data.pic_id)
        if not pic:
            raise HTTPException(status_code=404, detail="PIC not found")
        
        await projects_repo.add_pic(conn, project_id, data.pic_id, data.role)
    
    return {"success": True, "project_id": str(project_id), "pic_id": str(data.pic_id)}


@router.delete("/{project_id}/pics/{pic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_pic_from_project(
    project_id: uuid.UUID,
    pic_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> None:
    """Remove PIC from project."""
    async with pool.acquire() as conn:
        success = await projects_repo.remove_pic(conn, project_id, pic_id)
        if not success:
            raise HTTPException(status_code=404, detail="PIC not found in project")