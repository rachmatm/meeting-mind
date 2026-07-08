"""events_log repository.

Phase 2 ingest path (blueprint 3.1) needs two operations:

* `record_event` - INSERT ... ON CONFLICT (idempotency_key) DO NOTHING.
  Returns the stored row (or None if duplicate). The caller enqueues to
  pgmq only when this returns a row.
* `set_status` - update status field as the worker moves an event
  through received -> processing -> done | error.

Nothing else here touches events yet; Phase 3 (worker) loads the full
event by id when it picks a job off the queue.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

# Event lifecycle states. Mirrored as plain strings in the table column.
STATUS_RECEIVED = "received"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_ERROR = "error"

_UUID = type(uuid.uuid4())


async def record_event(
    conn: asyncpg.Connection,
    *,
    idempotency_key: str,
    source: str,
    raw_input: str,
    parsed_event: dict[str, Any] | None = None,
) -> asyncpg.Record | None:
    """Insert an event row. Returns None if `idempotency_key` already
    exists (duplicate, caller drops it). Otherwise returns the inserted
    row including the server-generated id and status='received'.
    """
    return await conn.fetchrow(
        """
        INSERT INTO events_log
            (idempotency_key, source, raw_input, parsed_event, status)
        VALUES ($1, $2, $3, $4, 'received')
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id, idempotency_key, source, status, created_at
        """,
        idempotency_key,
        source,
        raw_input,
        json.dumps(parsed_event) if parsed_event is not None else None,
    )


async def set_status(
    conn: asyncpg.Connection,
    *,
    event_id: uuid.UUID,
    status: str,
) -> None:
    """Move the lifecycle forward. Caller validates transitions; the
    repository only enforces that status is a known value via DB CHECK
    (added if needed in a later migration).
    """
    await conn.execute(
        "UPDATE events_log SET status = $2 WHERE id = $1",
        event_id,
        status,
    )
