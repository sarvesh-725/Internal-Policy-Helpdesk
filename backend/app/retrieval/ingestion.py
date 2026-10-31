import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.llm.gemini_embeddings import GeminiEmbeddingGateway
from app.persistence.models import (
    PolicyAccessRule,
    PolicyChunk,
    PolicyDocument,
    PolicyDocumentVersion,
    PolicyIngestionRecord,
)
from app.retrieval.chunking import chunk_policy_content
from app.retrieval.policy_source import DocumentStatus, PolicySourceDocument, PolicySourceError, load_policy_source
from app.retrieval.qdrant_store import QdrantPolicyStore, VectorPoint


class DuplicateActiveVersionError(ValueError):
    pass


@dataclass
class IngestionReport:
    ingested: int = 0
    quarantined: int = 0
    entries: list[dict[str, str]] = field(default_factory=list)

    def add(self, *, path: str, status: str, detail: str) -> None:
        self.entries.append({"path": path, "status": status, "detail": detail})
        if status == "ingested":
            self.ingested += 1
        elif status == "quarantined":
            self.quarantined += 1


class PolicyIngestionService:
    """Fail-closed policy ingestion from a curated local corpus into PostgreSQL and Qdrant."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        embeddings: GeminiEmbeddingGateway | None = None,
        vector_store: QdrantPolicyStore | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.embeddings = embeddings or GeminiEmbeddingGateway(self.settings)
        self.vector_store = vector_store or QdrantPolicyStore(self.settings)

    def ingest_all(self, knowledge_root: Path | None = None) -> IngestionReport:
        root = knowledge_root or self.settings.policy_knowledge_dir
        report = IngestionReport()
        if not root.exists() or not root.is_dir():
            raise PolicySourceError(f"Knowledge directory does not exist: {root}")

        domain_folders = {"hr", "it", "operations"}
        source_paths = sorted(
            path
            for path in root.rglob("*")
            if path.suffix.lower() in {".md", ".pdf"} and path.parent.name in domain_folders
        )
        if not source_paths:
            raise PolicySourceError("No Markdown or PDF policy sources were found.")

        for path in source_paths:
            relative_path = path.relative_to(root).as_posix()
            source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            try:
                source = load_policy_source(path, root)
                self.ingest_source(source)
                report.add(path=relative_path, status="ingested", detail="indexed")
            except (PolicySourceError, DuplicateActiveVersionError) as exc:
                self.session.rollback()
                reason_code = self._reason_code(exc)
                self._record_status(
                    source_path=relative_path,
                    source_hash=source_hash,
                    document_id=None,
                    status="quarantined",
                    reason_code=reason_code,
                    detail=self._safe_detail(exc),
                )
                report.add(path=relative_path, status="quarantined", detail=reason_code)
        return report

    def ingest_source(self, source: PolicySourceDocument) -> None:
        if source.metadata.status is not DocumentStatus.PUBLISHED:
            raise PolicySourceError("Only published policy documents may be indexed.")
        existing_document = self.session.scalar(
            select(PolicyDocument).where(PolicyDocument.document_id == source.metadata.document_id)
        )
        document = existing_document or PolicyDocument(
            document_id=source.metadata.document_id,
            title=source.metadata.title,
            domain=source.metadata.domain.value,
            status=source.metadata.status.value,
            owner_role=source.metadata.owner_role.value,
            source_path=source.relative_path,
            source_hash=source.source_hash,
            effective_date=source.metadata.effective_date,
            expires_at=source.metadata.expires_at,
        )
        if existing_document is None:
            self.session.add(document)
            self.session.flush()
        else:
            existing_version = self.session.scalar(
                select(PolicyDocumentVersion).where(
                    PolicyDocumentVersion.document_id == document.id,
                    PolicyDocumentVersion.version == source.metadata.version,
                )
            )
            if existing_version is not None:
                if document.source_hash == source.source_hash:
                    return
                raise DuplicateActiveVersionError("A document version already exists.")
            self.session.execute(
                update(PolicyDocumentVersion)
                .where(PolicyDocumentVersion.document_id == document.id)
                .values(is_active=False)
            )
            self.session.execute(delete(PolicyAccessRule).where(PolicyAccessRule.document_id == document.id))
            self._update_document(document, source)

        version = PolicyDocumentVersion(
            document_id=document.id,
            version=source.metadata.version,
            review_due_date=source.metadata.review_due_date,
            is_active=True,
        )
        self.session.add(version)
        self.session.flush()

        for role in source.metadata.allowed_roles:
            for region in source.metadata.allowed_regions:
                self.session.add(PolicyAccessRule(document_id=document.id, role=role.value, region=region))

        drafts = chunk_policy_content(
            source.content,
            chunk_size=self.settings.policy_chunk_size,
            overlap=self.settings.policy_chunk_overlap,
        )
        chunks = [
            PolicyChunk(
                document_version_id=version.id,
                section_id=draft.section_id,
                ordinal=draft.ordinal,
                content=draft.content,
                content_hash=draft.content_hash,
            )
            for draft in drafts
        ]
        self.session.add_all(chunks)
        self.session.flush()

        vectors = self.embeddings.embed_documents([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
            raise RuntimeError("Embedding count does not match policy chunk count.")
        self.vector_store.ensure_collection(len(vectors[0]))
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk.qdrant_point_id = str(chunk.id)
            points.append(
                VectorPoint(
                    point_id=chunk.id,
                    vector=vector,
                    payload={
                        "chunk_id": str(chunk.id),
                        "document_id": document.document_id,
                        "document_version_id": str(version.id),
                        "domain": document.domain,
                        "status": document.status,
                    },
                )
            )
        self.vector_store.upsert(points)
        self.session.commit()
        self._record_status(
            source_path=source.relative_path,
            source_hash=source.source_hash,
            document_id=document.document_id,
            status="ingested",
            reason_code=None,
            detail="Indexed into PostgreSQL and Qdrant.",
        )

    def _update_document(self, document: PolicyDocument, source: PolicySourceDocument) -> None:
        document.title = source.metadata.title
        document.domain = source.metadata.domain.value
        document.status = source.metadata.status.value
        document.owner_role = source.metadata.owner_role.value
        document.source_path = source.relative_path
        document.source_hash = source.source_hash
        document.effective_date = source.metadata.effective_date
        document.expires_at = source.metadata.expires_at

    def _record_status(
        self,
        *,
        source_path: str,
        source_hash: str,
        document_id: str | None,
        status: str,
        reason_code: str | None,
        detail: str,
    ) -> None:
        self.session.add(
            PolicyIngestionRecord(
                source_path=source_path,
                source_hash=source_hash,
                document_id=document_id,
                status=status,
                reason_code=reason_code,
                detail=detail[:500],
            )
        )
        self.session.commit()

    @staticmethod
    def _reason_code(error: Exception) -> str:
        if isinstance(error, DuplicateActiveVersionError):
            return "duplicate_active_version"
        if isinstance(error, PolicySourceError):
            return "invalid_policy_source"
        return "ingestion_failed"

    @staticmethod
    def _safe_detail(error: Exception) -> str:
        return type(error).__name__.replace("Error", " error")
