"""Liveness + Neon reachability.

Returns 200 only when both the process is up and SELECT 1 against Neon
succeeds. Anything else is 503 so a load balancer drops a broken pod.
Blueprint section 12.4.
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    pool: asyncpg.Pool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "starting", "db": "no_pool"},
        )

    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
    except Exception as exc:  # network / auth / etc.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "db": "unreachable", "error": repr(exc)},
        )

    return JSONResponse(status_code=200, content={"status": "ok", "db": "reachable"})
