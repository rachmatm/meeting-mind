# Work Log

## [2026-07-08] Phase 0 & 1 Review

### What Was Built/Changed

**Phase 0 - Project scaffold (COMPLETE)**
- FastAPI gateway with `/health` endpoint
- Database pool management with asyncpg
- Settings via pydantic-settings reading from `.env`
- Dockerfile and docker-compose.yml for gateway + worker
- Worker placeholder (Phase 0 idle loop)

**Phase 1 - Data layer (CODE COMPLETE, NOT APPLIED)**
- Migration runner (`services/hermes/migrations/runner.py`)
- SQL migrations:
  - `0001_init.sql`: All tables (tasks, user_preferences, events_log, decisions_log, memory_vectors) with pgvector extension
  - `0002_indexes.sql`: HNSW index on memory_vectors.embedding
- Repository layer (`services/hermes/repositories/events.py`)

### Key Decisions & Tradeoffs
- Plain SQL migrations over Alembic (simpler, no ORM)
- Vector dimension set to 1024 (voyage-3 default)
- UUIDs for all primary keys (via pgcrypto)
- Pool timeout increased to 60s for Neon connection latency

### Known Issues / Things to Double-check
- ~~Migrations have NOT been run against the database yet~~ - RESOLVED 2026-07-08: migrations executed, all 6 tables present
- ~~Neon connection currently failing (possibly paused)~~ - RESOLVED 2026-07-08: connection working, health probe returns OK
- ~~Gateway health endpoint shows db:unreachable~~ - RESOLVED 2026-07-08: Neon reachable, HNSW index verified

### Files Touched
- `services/hermes/core/db.py` - added timeout=60 to pool creation
- `.env` - created from .envy, fixed LLM_API_KEY naming
