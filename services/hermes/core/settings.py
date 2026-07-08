"""Application settings loaded from environment / .env.

Phase 0 contract: fail fast on required secrets. Blueprint section 12.6.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All env-driven config for gateway and worker.

    Secrets use SecretStr so they don't leak in repr/logs.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Neon / Postgres ---------------------------------------------------
    # Plain str on purpose: asyncpg wants a real string, and PostgresDsn had
    # to be coerced at every call site. Format validated in CI smoke test.
    neon_dsn: str  # required: postgresql://...?sslmode=require
    neon_pool_min_size: int = 1
    neon_pool_max_size: int = 10

    # --- LLM ---------------------------------------------------------------
    # OpenAI-compatible client against a third-party proxy (api.iamhc.cn).
    # Phase 0: settings fail-fast on missing LLM_API_KEY. Worker wiring
    # (tool calls, native tool-use) is wired in Phase 3.
    llm_base_url: str = "https://api.iamhc.cn/v1"
    llm_api_key: SecretStr = Field(...)
    llm_model: str = "MiniMax-M3"
    # Per-call caps carried in settings so they can be tuned without code.
    llm_max_tokens: int = 1024

    # --- Embeddings (fixed contract with pgvector dimension, Phase 1+4) ----
    embedding_provider: str = "voyage"
    embedding_model: str = "voyage-3"
    embedding_dim: int = 1024  # voyage-3 default
    voyage_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None

    # --- n8n / webhook auth -----------------------------------------------
    n8n_shared_secret: SecretStr = Field(...)  # required (Phase 2)
    webhook_signature_header: str = "X-Hub-Signature-256"

    # --- Langfuse (Phase 4) -----------------------------------------------
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- Server ------------------------------------------------------------
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000

    # --- Queue -------------------------------------------------------------
    queue_name: str = "hermes_events"

    # --- Notion (Phase 2) --------------------------------------------------
    notion_api_key: SecretStr | None = None
    notion_database_id: str | None = None  # Default database for tasks

    # --- Qdrant (Phase 2) --------------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None

    # --- Notifications (Phase 2) -------------------------------------------
    slack_bot_token: SecretStr | None = None
    slack_signing_secret: SecretStr | None = None
    whatsapp_api_url: SecretStr | None = None
    whatsapp_api_token: SecretStr | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. First call validates all required env vars."""
    return Settings()  # type: ignore[call-arg]
