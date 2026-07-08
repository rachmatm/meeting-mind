"""Message queue client using pgmq.

Phase 3: Worker polls this queue for events to process.
"""

from __future__ import annotations

import json
from typing import Any

from services.hermes.core.settings import get_settings


class MessageQueue:
    """PostgreSQL message queue using pgmq."""
    
    def __init__(self):
        settings = get_settings()
        self.queue_name = settings.queue_name
        self._conn = None
    
    async def _get_conn(self):
        """Get database connection."""
        import asyncpg
        from services.hermes.core.db import create_pool
        
        if self._conn is None:
            settings = get_settings()
            pool = await create_pool(settings)
            self._conn = await pool.acquire()
        return self._conn
    
    async def enqueue(self, message: dict[str, Any]) -> int:
        """Add message to queue.
        
        Args:
            message: Dict to enqueue (will be JSON serialized)
            
        Returns:
            Message ID
        """
        conn = await self._get_conn()
        
        # Use pgmq if available, otherwise simple table-based queue
        try:
            result = await conn.fetchval(
                "SELECT pgmq.enqueue($1, $2)",
                self.queue_name,
                json.dumps(message),
            )
            return result
        except Exception:
            # Fallback: insert into simple queue table
            return await self._fallback_enqueue(conn, message)
    
    async def _fallback_enqueue(self, conn, message: dict[str, Any]) -> int:
        """Fallback queue using simple table."""
        # Create queue table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS worker_queue (
                id SERIAL PRIMARY KEY,
                payload JSONB NOT NULL,
                enqueued_at TIMESTAMPTZ DEFAULT NOW(),
                processed BOOLEAN DEFAULT FALSE
            )
        """)
        
        # Insert message
        row = await conn.fetchrow(
            "INSERT INTO worker_queue (payload) VALUES ($1) RETURNING id",
            json.dumps(message),
        )
        return row["id"]
    
    async def dequeue(self, timeout: int = 5) -> dict[str, Any] | None:
        """Get next message from queue (blocking poll).
        
        Args:
            timeout: Poll timeout in seconds
            
        Returns:
            Message dict or None if empty
        """
        conn = await self._get_conn()
        
        try:
            # Try pgmq first
            result = await conn.fetchrow(
                "SELECT * FROM pgmq.read($1, 1, $2)",
                self.queue_name,
                timeout,
            )
            if result:
                return {
                    "message_id": result["msg_id"],
                    "payload": json.loads(result["message"]),
                }
        except Exception:
            # Fallback to simple queue
            return await self._fallback_dequeue(conn)
        
        return None
    
    async def _fallback_dequeue(self, conn) -> dict[str, Any] | None:
        """Fallback dequeue using simple table."""
        row = await conn.fetchrow("""
            SELECT id, payload FROM worker_queue
            WHERE processed = FALSE
            ORDER BY enqueued_at
            LIMIT 1
        """)
        
        if row:
            return {
                "message_id": row["id"],
                "payload": dict(row["payload"]),
            }
        return None
    
    async def complete(self, message_id: int) -> None:
        """Mark message as processed and remove from queue.
        
        Args:
            message_id: Message ID to complete
        """
        conn = await self._get_conn()
        
        try:
            await conn.execute("SELECT pgmq.archive($1, $2)", self.queue_name, message_id)
        except Exception:
            # Fallback: mark as processed
            await conn.execute(
                "UPDATE worker_queue SET processed = TRUE WHERE id = $1",
                message_id,
            )
    
    async def close(self) -> None:
        """Close connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None


# Singleton
_queue: MessageQueue | None = None


def get_queue() -> MessageQueue:
    """Get or create queue singleton."""
    global _queue
    if _queue is None:
        _queue = MessageQueue()
    return _queue


async def enqueue_event(event_type: str, payload: dict[str, Any]) -> int:
    """Convenience function to enqueue an event."""
    queue = get_queue()
    message = {
        "event_type": event_type,
        "payload": payload,
    }
    return await queue.enqueue(message)