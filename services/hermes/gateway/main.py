"""FastAPI entry point. Owns the asyncio DB pool lifecycle.

Phase 0 surface: only GET /health. POST /event, auth, dedup, queue land in
Phase 2 (blueprint sections 3.1 and 12.4).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI

from services.hermes.core.db import create_pool
from services.hermes.core.settings import get_settings
from services.hermes.gateway.routes import health


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
    app.include_router(health.router)
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
