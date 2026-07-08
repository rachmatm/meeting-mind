-- 0001_init.sql
-- Phase 1 schema. Blueprint section 5. Idempotent: safe to re-run.
--
-- Why these are idempotent:
--   * CREATE EXTENSION IF NOT EXISTS
--   * CREATE TABLE IF NOT EXISTS
--   * CREATE INDEX ... ON ... (no IF NOT EXISTS form). We track applied
--     migrations in `schema_migrations` and skip already-applied files,
--     so the index is created exactly once. If you re-run by hand on a
--     fresh DB the indexes are created on first apply.
--
-- Why UUIDs:
--   blueprint Section 5 uses UUID primary keys for tasks / events_log /
--   decisions_log / memory_vectors. pgcrypto gives gen_random_uuid().
--
-- Why vector(1024):
--   Phase 1 contract on embedding dim. Pin to voyage-3 (already default
--   in core/settings.py). Changing this means re-embedding all stored
--   memory (blueprint 4.2).

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- =========================================================================
-- Structured state
-- =========================================================================

CREATE TABLE IF NOT EXISTS tasks (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title      TEXT,
    status     TEXT,
    deadline   TIMESTAMPTZ,
    user_id    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_preferences (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    TEXT,
    key        TEXT,
    value      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================================================
-- Event ingest with dedup. idempotency_key uniqueness is the at-least-once
-- safety net that makes duplicate deliveries safe (blueprint 3.1, 8).
-- =========================================================================

CREATE TABLE IF NOT EXISTS events_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key TEXT UNIQUE,
    source          TEXT,
    raw_input       TEXT,
    parsed_event    JSONB,
    status          TEXT NOT NULL DEFAULT 'received',  -- received | processing | done | error
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================================================
-- Decision audit trail. tool_call / tool_result capture the native Claude
-- tool_use block (blueprint 6.2). Token counts power cost observability.
-- =========================================================================

CREATE TABLE IF NOT EXISTS decisions_log (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id       UUID REFERENCES events_log(id),
    action         TEXT,
    reason         TEXT,
    tool_call      JSONB,
    tool_result    JSONB,
    model          TEXT,
    input_tokens   INT,
    output_tokens  INT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================================================
-- Semantic memory (pgvector). dim locked to 1024 (voyage-3) for the MVP.
-- =========================================================================

CREATE TABLE IF NOT EXISTS memory_vectors (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT,
    type        TEXT,                  -- preference | insight | summary
    content     TEXT,
    importance  TEXT,                  -- low | medium | high
    embedding   vector(1024),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
