# Migrations

Numbered plain-SQL files applied in lexicographic order. The runner
(`python -m services.hermes.migrations.runner`) tracks applied files in
`schema_migrations` and skips them on re-run.

## Why not Alembic

No ORM in MVP. A bespoke runner keeps schema definitions in `.sql` files
editable with psql, no Python decision layer between author and database.

## Conventions

- Filename: `NNNN_short_name.sql`, zero-padded four-digit prefix.
- One transaction per file (auto-wrapped by the runner).
- Re-running the runner is safe; it is the Phase 1 exit criterion.
- Schema changes that touch existing rows ship in a follow-up file -
  never edited in place once applied.
