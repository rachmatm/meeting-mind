"""Async Postgres pool shared by gateway and worker.

One pool per process. Gateway opens in lifespan; worker opens at startup.
All SQL lives in repositories/; routes and business logic never touch raw SQL.
Blueprint section 12.6.
"""

from __future__ import annotations

import asyncpg

from services.hermes.core.settings import Settings


async def create_pool(settings: Settings) -> asyncpg.Pool:
    """Open a pool. Neon requires SSL; the DSN already pins sslmode=require."""
    return await asyncpg.create_pool(
        settings.neon_dsn,
        min_size=settings.neon_pool_min_size,
        max_size=settings.neon_pool_max_size,
        command_timeout=10,
        timeout=60,  # Neon connections can be slow to establish
    )


async def ping(pool: asyncpg.Pool) -> None:
    """Trivial liveness probe. Raises if Neon is unreachable."""
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
