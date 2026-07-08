"""Task API routes per blueprint section 10."""

from __future__ import annotations

import uuid
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from services.hermes.gateway.schemas import (
    TaskConfirmRequest,
    TaskConfirmResponse,
    TaskCreate,
    TaskDetailResponse,
    TaskResponse,
    TaskUpdate,
)
from services.hermes.repositories import tasks as tasks_repo
from services.hermes.repositories import meetings as meetings_repo
from services.hermes.repositories import projects as projects_repo
from services.hermes.repositories import pics as pics_repo


def get_pool(request: Request) -> asyncpg.Pool:
    """Get DB pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    pool: asyncpg.Pool = Depends(get_pool),
) -> TaskResponse:
    """Create a new task."""
    async with pool.acquire() as conn:
        # Verify project exists
        project = await projects_repo.get_by_id(conn, data.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        task = await tasks_repo.create(
            conn,
            project_id=data.project_id,
            division=data.division,
            description=data.description,
            pic_id=data.pic_id,
            deadline=data.deadline,
            status=data.status,
        )
    return TaskResponse(**dict(task))


@router.get("", response_model=list[TaskDetailResponse])
async def list_tasks(
    project_id: uuid.UUID | None = None,
    pic_id: uuid.UUID | None = None,
    task_status: str | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[TaskDetailResponse]:
    """List tasks with optional filters."""
    async with pool.acquire() as conn:
        if project_id:
            task_list = await tasks_repo.get_by_project(conn, project_id)
        elif pic_id:
            task_list = await tasks_repo.get_by_pic(conn, pic_id)
        elif task_status:
            task_list = await tasks_repo.get_by_status(conn, task_status)
        else:
            # Return all tasks
            task_list = await conn.fetch("SELECT * FROM tasks ORDER BY created_at DESC")
    
    # Enrich with project and PIC names
    result = []
    for t in task_list:
        task_dict = dict(t)
        if task_dict.get("project_id"):
            project = await projects_repo.get_by_id(conn, task_dict["project_id"])
            task_dict["project_name"] = project["name"] if project else None
        if task_dict.get("pic_id"):
            pic = await pics_repo.get_by_id(conn, task_dict["pic_id"])
            task_dict["pic_name"] = pic["name"] if pic else None
        result.append(TaskDetailResponse(**task_dict))
    
    return result


@router.get("/due-soon")
async def get_due_soon(
    days: int = 1,
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[TaskDetailResponse]:
    """Get tasks due within N days."""
    async with pool.acquire() as conn:
        task_list = await tasks_repo.get_due_soon(conn, days)
    
    return [TaskDetailResponse(**dict(t)) for t in task_list]


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: Annotated[uuid.UUID, Path(description="Task UUID")],
    pool: asyncpg.Pool = Depends(get_pool),
) -> TaskDetailResponse:
    """Get task details."""
    async with pool.acquire() as conn:
        task = await tasks_repo.get_by_id(conn, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
    
    task_dict = dict(task)
    if task_dict.get("project_id"):
        project = await projects_repo.get_by_id(conn, task_dict["project_id"])
        task_dict["project_name"] = project["name"] if project else None
    if task_dict.get("pic_id"):
        pic = await pics_repo.get_by_id(conn, task_dict["pic_id"])
        task_dict["pic_name"] = pic["name"] if pic else None
    
    return TaskDetailResponse(**task_dict)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    data: TaskUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
) -> TaskResponse:
    """Update task details."""
    async with pool.acquire() as conn:
        task = await tasks_repo.update(
            conn,
            task_id,
            division=data.division,
            description=data.description,
            pic_id=data.pic_id,
            deadline=data.deadline,
            status=data.status,
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(**dict(task))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> None:
    """Delete task."""
    async with pool.acquire() as conn:
        success = await tasks_repo.delete(conn, task_id)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found")


# --- Task confirmation (end of workflow) ---

@router.post("/confirm", response_model=TaskConfirmResponse)
async def confirm_tasks(
    data: TaskConfirmRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> TaskConfirmResponse:
    """Confirm PIC assignments and create tasks in Notion.
    
    This is the final step in the workflow after PIC confirmation.
    Creates tasks in DB and triggers Notion integration.
    """
    tasks_created = 0
    
    async with pool.acquire() as conn:
        # Verify meeting exists and is approved
        meeting = await meetings_repo.get_by_id(conn, data.meeting_id)
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        if meeting["status"] != "approved":
            raise HTTPException(status_code=400, detail="Meeting must be approved first")
        
        # Create each task
        for task_data in data.tasks:
            await tasks_repo.create(
                conn,
                project_id=task_data.project_id,
                division=task_data.division,
                description=task_data.description,
                pic_id=task_data.pic_id,
                deadline=task_data.deadline,
                meeting_id=data.meeting_id,
                status="todo",
            )
            tasks_created += 1
        
        # TODO: Trigger Notion integration
        # notion_url = await create_notion_page(project_id, tasks)
        notion_url = None
    
    return TaskConfirmResponse(
        tasks_created=tasks_created,
        notion_page_url=notion_url,
    )