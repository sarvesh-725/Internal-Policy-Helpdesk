from sqlalchemy import text

from app.config import Settings, get_settings
from app.persistence.database import engine
from app.retrieval.qdrant_store import QdrantPolicyStore


class DependencyUnavailableError(RuntimeError):
    """Internal-only readiness signal; callers intentionally receive no dependency details."""


class ReadinessService:
    """Checks mandatory local runtime dependencies without invoking Gemini or exposing diagnostics."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def check(self) -> None:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            QdrantPolicyStore(self.settings).client.get_collections()
        except Exception as exc:
            raise DependencyUnavailableError("A required runtime dependency is unavailable.") from exc
