"""Hermes worker entry point.

Phase 3: Long-poll pgmq -> hydrate state -> execute workflow -> persist -> delete message.
"""

from __future__ import annotations

import asyncio
import logging

from services.hermes.worker.executor import run_worker

log = logging.getLogger("hermes.worker")


async def main() -> None:
    """Run the worker with the workflow executor."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    await run_worker()


if __name__ == "__main__":
    asyncio.run(main())
