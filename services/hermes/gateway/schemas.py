"""Pydantic schemas for API request/response validation.

Phase 2 per blueprint section 10.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from pydantic import BaseModel, Field
import uuid


# --- PIC Schemas ---

class PICCreate(BaseModel):
    user_id: str
    name: str
    type: str = "person"
    email: str | None = None
    slack_id: str | None = None
    divisions: list[str] | None = None
    responsibilities: list[str] | None = None
    skills: list[str] | None = None
    max_concurrent_tasks: int = 5
    manager_id: uuid.UUID | None = None


class PICContactCreate(BaseModel):
    contact_type: str = Field(..., pattern="^(whatsapp|email|slack)$")
    contact_value: str
    person_name: str
    is_primary: bool = False


class PICContactResponse(BaseModel):
    id: uuid.UUID
    contact_type: str
    contact_value: str
    person_name: str
    is_primary: bool


class PICResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    name: str
    type: str
    email: str | None
    slack_id: str | None
    divisions: list[str] | None
    responsibilities: list[str] | None
    skills: list[str] | None
    max_concurrent_tasks: int
    manager_id: uuid.UUID | None
    is_active: bool
    created_at: Any
    updated_at: Any
    
    model_config = {"from_attributes": True}


class PICDetailResponse(PICResponse):
    contacts: list[PICContactResponse] = []


# --- Project Schemas ---

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    notion_page_id: str | None = None


class ProjectPICAdd(BaseModel):
    pic_id: uuid.UUID
    role: str = "member"


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    notion_page_id: str | None
    created_at: Any
    
    model_config = {"from_attributes": True}


class ProjectDetailResponse(ProjectResponse):
    pics: list[dict] = []


# --- Meeting Schemas ---

class MeetingCreate(BaseModel):
    transcript: str
    project_id: uuid.UUID | None = None
    title: str | None = None
    audio_url: str | None = None


class MeetingUpdate(BaseModel):
    project_id: uuid.UUID | None = None
    title: str | None = None
    transcript: str | None = None
    summary: dict[str, Any] | None = None
    audio_url: str | None = None
    status: str | None = None


class MeetingResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str | None
    transcript: str
    summary: dict[str, Any] | None
    audio_url: str | None
    status: str
    created_at: Any
    updated_at: Any
    
    model_config = {"from_attributes": True}


# --- Task Schemas ---

class TaskCreate(BaseModel):
    project_id: uuid.UUID
    division: str
    description: str
    pic_id: uuid.UUID | None = None
    deadline: date | None = None
    status: str = "todo"


class TaskUpdate(BaseModel):
    division: str | None = None
    description: str | None = None
    pic_id: uuid.UUID | None = None
    deadline: date | None = None
    status: str | None = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    division: str
    description: str
    pic_id: uuid.UUID | None
    deadline: date | None
    status: str
    meeting_id: uuid.UUID | None
    created_at: Any
    updated_at: Any
    
    model_config = {"from_attributes": True}


class TaskDetailResponse(TaskResponse):
    project_name: str | None = None
    pic_name: str | None = None


# --- Upload Schemas ---

class UploadResponse(BaseModel):
    meeting_id: uuid.UUID
    transcript: str
    status: str = "pending"


class TranscriptApproveRequest(BaseModel):
    project_id: uuid.UUID


class TaskConfirmRequest(BaseModel):
    tasks: list[TaskCreate]
    meeting_id: uuid.UUID


class TaskConfirmResponse(BaseModel):
    tasks_created: int
    notion_page_url: str | None = None