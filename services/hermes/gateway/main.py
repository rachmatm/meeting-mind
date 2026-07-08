"""FastAPI entry point. Owns the asyncio DB pool lifecycle.

Phase 1: Full API surface per blueprint sections 3.1 and 10.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI

from services.hermes.core.db import create_pool
from services.hermes.core.settings import get_settings
from services.hermes.gateway.routes import health, pics, projects, meetings, upload, tasks, workflow


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool = await create_pool(settings)
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Hermes Gateway", lifespan=lifespan)
    
    # Routes
    app.include_router(health.router)
    app.include_router(pics.router)
    app.include_router(projects.router)
    app.include_router(meetings.router)
    app.include_router(upload.router)
    app.include_router(tasks.router)
    app.include_router(workflow.router)
    
    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "services.hermes.gateway.main:app",
        host=settings.gateway_host,
        port=settings.gateway_port,
        reload=False,
    )
