# Meeting Mind

AI-powered meeting orchestration system that helps teams run more effective meetings through intelligent automation.

## Features

- AI-driven meeting coordination and follow-ups
- Task extraction and assignment from meeting notes
- Integration with calendar and messaging platforms
- Configurable workflows for different meeting types

## Quick Start

```bash
# Start the services
docker compose up -d

# Run migrations
docker compose exec gateway python -m services.openclaw.migrations.runner

# Access the API
curl http://localhost:8000/health
```

## Architecture

- **Gateway**: FastAPI-based HTTP API
- **Worker**: Background task processor
- **Database**: PostgreSQL for persistent storage

See BLUEPRINT.md and PRD.md for detailed documentation.
