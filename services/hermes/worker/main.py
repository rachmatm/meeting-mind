"""Hermes worker entry point.

Phase 3 will replace this empty loop with: long-poll pgmq -> hydrate state
-> call Claude with tools -> execute -> persist decision -> delete message.

For Phase 0 the worker only proves topology (separate container, opens its
own pool) so docker-compose exposes the two-process shape from day one.
"""

from __future__ import annotations

import asyncio
import logging

from services.hermes.core.db import create_pool
from services.hermes.core.settings import get_settings

log = logging.getLogger("hermes.worker")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    pool = await create_pool(settings)
    log.info("worker idle (Phase 0 placeholder); pool open")
    try:
        # Idle loop. The real loop arrives in Phase 3.
        stop = asyncio.Event()
        try:
            await stop.wait()
        except asyncio.CancelledError:
            pass
    finally:
        await pool.close()
        log.info("worker shut down")


if __name__ == "__main__":
    asyncio.run(main())
