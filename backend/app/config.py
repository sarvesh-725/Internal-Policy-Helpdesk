from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-only runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "Dynamic Enterprise Support Swarm"
    api_v1_prefix: str = "/api/v1"
    backend_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    database_url: str = "postgresql+psycopg://nodeswarm_app:nodeswarm_app_dev_only@postgres:5432/nodeswarm"
    database_migration_url: str = "postgresql+psycopg://nodeswarm:nodeswarm_dev_only@postgres:5432/nodeswarm"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "policy_chunks"
    policy_knowledge_dir: Path = Path("knowledge")
    gemini_embedding_model: str = "gemini-embedding-001"
    policy_chunk_size: int = 1_400
    policy_chunk_overlap: int = 160

    keycloak_issuer_url: str = "http://keycloak:8080/realms/nodeswarm"
    keycloak_audience: str = "nodeswarm-api"
    keycloak_jwks_url: str = "http://keycloak:8080/realms/nodeswarm/protocol/openid-connect/certs"

    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    llm_router_model: str = "gemini-2.5-flash"
    llm_synthesis_model: str = "gemini-2.5-pro"

    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "nodeswarm"
    presidio_enabled: bool = True
    input_max_characters: int = 8_000
    gemini_timeout_seconds: int = 30
    model_max_output_tokens: int = 1_200
    retrieval_retry_attempts: int = 2
    otel_exporter_otlp_endpoint: str | None = None
    max_domain_handoffs: int = 2
    max_total_steps: int = 8

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
