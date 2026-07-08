-- 0002_indexes.sql
-- Phase 1 indexes. Blueprint Section 5: HNSW on memory_vectors.embedding
-- and UNIQUE on events_log.idempotency_key (the latter is also created in
-- 0001 via the UNIQUE column constraint, but the explicit index name is
-- stable for query plans).
--
-- This file is NOT marked idempotent at the SQL level (Postgres prior
-- to 16 lacks CREATE INDEX IF NOT EXISTS). The runner tracks application
-- in schema_migrations so this runs exactly once per database.

CREATE INDEX memory_vectors_embedding_hnsw
    ON memory_vectors USING hnsw (embedding vector_cosine_ops);
