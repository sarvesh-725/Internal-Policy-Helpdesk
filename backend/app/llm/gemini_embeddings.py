from collections.abc import Sequence

from google import genai
from google.genai import types

from app.config import Settings, get_settings


class EmbeddingConfigurationError(RuntimeError):
    pass


class GeminiEmbeddingGateway:
    """Small server-only Gemini adapter for policy-document and query embeddings."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.gemini_api_key:
            raise EmbeddingConfigurationError("GEMINI_API_KEY is required for policy ingestion and retrieval.")
        self.client = genai.Client(api_key=self.settings.gemini_api_key)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, task_type="RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        embeddings = self._embed([text], task_type="RETRIEVAL_QUERY")
        return embeddings[0]

    def _embed(self, texts: Sequence[str], *, task_type: str) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.models.embed_content(
            model=self.settings.gemini_embedding_model,
            contents=list(texts),
            config=types.EmbedContentConfig(task_type=task_type),
        )
        embeddings = getattr(response, "embeddings", None)
        if not embeddings or len(embeddings) != len(texts):
            raise RuntimeError("Gemini returned an incomplete embedding response.")
        return [list(embedding.values) for embedding in embeddings]
