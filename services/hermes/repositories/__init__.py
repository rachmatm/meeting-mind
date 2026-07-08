"""Repository package.

Async DB access. Raw SQL lives here and in the migration .sql files
only. Routes and business logic import these functions, never execute
SQL themselves.

Blueprint section 12.3 lists one module per table. Phase 1 ships the
events module because Phase 2 needs it; the rest arrive with the worker.
"""
