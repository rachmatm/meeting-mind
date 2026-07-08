FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# uv is a single static binary; copy it from the official image so we keep
# the runtime image small and avoid the shell install dance.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependency layer is cached separately from source so code edits don't
# reinstall everything.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project --no-dev

COPY services ./services
RUN uv sync --no-dev

# Non-root for runtime. Image stays slim: no gcc, no dev headers needed.
RUN useradd --uid 1000 --create-home hermes && chown -R hermes:hermes /app
USER hermes

EXPOSE 8000

# Default command is the gateway; the docker-compose worker service
# overrides this with the worker entry point.
CMD ["python", "-m", "uvicorn", "services.hermes.gateway.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
