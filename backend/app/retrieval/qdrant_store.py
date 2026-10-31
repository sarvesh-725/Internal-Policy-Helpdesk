from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from app.config import Settings, get_settings
from app.schemas import Domain


@dataclass(frozen=True)
class VectorPoint:
    point_id: UUID
    vector: list[float]
    payload: dict[str, str | list[str]]


class QdrantPolicyStore:
    """Owns vector operations; all filters originate from server-validated data."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = QdrantClient(url=self.settings.qdrant_url)

    @property
    def collection_name(self) -> str:
        return self.settings.qdrant_collection

    def ensure_collection(self, vector_size: int) -> None:
        if vector_size <= 0:
            raise ValueError("Embedding vector size must be positive.")
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def upsert(self, points: Iterable[VectorPoint]) -> None:
        point_structs = [PointStruct(id=str(point.point_id), vector=point.vector, payload=point.payload) for point in points]
        if point_structs:
            self.client.upsert(collection_name=self.collection_name, points=point_structs, wait=True)

    def delete(self, point_ids: Sequence[UUID]) -> None:
        if point_ids:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=[str(point_id) for point_id in point_ids]),
                wait=True,
            )

    def search(
        self,
        *,
        query_vector: list[float],
        domain: Domain,
        document_version_ids: Sequence[UUID],
        limit: int,
    ):
        if not document_version_ids:
            return []
        query_filter = Filter(
            must=[
                FieldCondition(key="domain", match=MatchValue(value=domain.value)),
                FieldCondition(
                    key="document_version_id",
                    match=MatchAny(any=[str(document_version_id) for document_version_id in document_version_ids]),
                ),
            ]
        )
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return response.points
