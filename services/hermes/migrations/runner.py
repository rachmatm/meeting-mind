"""SQL migration runner.

The blueprint's Phase 1 says "alembic or plain SQL files run in order."
Plain SQL wins because there is no ORM and every byte of schema lives in
one readable spot. A 100-line runner is the only Python that knows how
the files are organized.

Run from the project root:
    uv run python -m services.hermes.migrations.runner
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import asyncpg

from services.hermes.core.db import create_pool
from services.hermes.core.settings import get_settings

log = logging.getLogger("hermes.migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parent


async def _ensure_tracking_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename   TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


async def _applied(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT filename FROM schema_migrations")
    return {r["filename"] for r in rows}


async def _apply(conn: asyncpg.Connection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    # One implicit transaction per file: part of the file always applies, or
    # nothing does, so a partial failure can't leave a half-migrated DB.
    async with conn.transaction():
        await conn.execute(sql)
        await conn.execute(
            "INSERT INTO schema_migrations (filename) VALUES ($1)",
            path.name,
        )
    log.info("applied %s", path.name)


async def run() -> None:
    settings = get_settings()
    pool = await create_pool(settings)

    files = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        log.warning("no .sql files in %s", MIGRATIONS_DIR)
        await pool.close()
        return

    applied = 0
    async with pool.acquire() as conn:
        await _ensure_tracking_table(conn)
        done = await _applied(conn)
        for name in files:
            if name in done:
                continue
            await _apply(conn, MIGRATIONS_DIR / name)
            applied += 1

    await pool.close()
    log.info("migrations finished (%d new of %d total)", applied, len(files))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(run())
    except Exception as exc:  # pragma: no cover - CLI banner
        log.error("migration failed: %s", exc)
        sys.exit(1)
