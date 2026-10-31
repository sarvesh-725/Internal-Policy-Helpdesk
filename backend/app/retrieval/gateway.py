import re
from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.llm.gemini_embeddings import GeminiEmbeddingGateway
from app.persistence.models import PolicyAccessRule, PolicyChunk, PolicyDocument, PolicyDocumentVersion
from app.policy.enforcement import PolicyEnforcementPoint
from app.retrieval.qdrant_store import QdrantPolicyStore
from app.schemas import AuthorizedChunk, CapabilitySet, CitationRef, Domain, Role, UserContext


class RetrievalAccessDenied(PermissionError):
    pass


class PolicyRetrievalGateway:
    """The only path from an authorized request to policy content."""

    def __init__(
        self,
        session: Session,
        *,
        policy_enforcement: PolicyEnforcementPoint | None = None,
        embeddings: GeminiEmbeddingGateway | None = None,
        vector_store: QdrantPolicyStore | None = None,
    ) -> None:
        self.session = session
        self.policy_enforcement = policy_enforcement or PolicyEnforcementPoint()
        self.embeddings = embeddings or GeminiEmbeddingGateway()
        self.vector_store = vector_store or QdrantPolicyStore()

    def search_policy(
        self,
        *,
        domain: Domain,
        query: str,
        user: UserContext,
        capabilities: CapabilitySet,
        max_results: int = 4,
    ) -> list[AuthorizedChunk]:
        decision = self.policy_enforcement.authorize_domain_search(capabilities, domain)
        if not decision.allowed:
            raise RetrievalAccessDenied(decision.reason_code)

        normalized_query = normalize_query(query)
        allowed_versions = self._allowed_document_versions(domain=domain, user=user, capabilities=capabilities)
        if not allowed_versions:
            return []

        query_vector = self.embeddings.embed_query(normalized_query)
        candidates = self.vector_store.search(
            query_vector=query_vector,
            domain=domain,
            document_version_ids=list(allowed_versions),
            limit=min(max(1, max_results), 4),
        )

        findings: list[AuthorizedChunk] = []
        seen_chunk_ids: set[UUID] = set()
        for candidate in candidates:
            payload = candidate.payload or {}
            chunk_id = parse_uuid(payload.get("chunk_id"))
            if chunk_id is None or chunk_id in seen_chunk_ids:
                continue
            authorized_chunk = self._reauthorize_candidate(
                chunk_id=chunk_id,
                expected_domain=domain,
                expected_versions=allowed_versions,
                user=user,
                capabilities=capabilities,
                score=float(candidate.score),
            )
            if authorized_chunk is not None:
                findings.append(authorized_chunk)
                seen_chunk_ids.add(chunk_id)
        return findings

    def _allowed_document_versions(
        self, *, domain: Domain, user: UserContext, capabilities: CapabilitySet
    ) -> set[UUID]:
        today = date.today()
        role_values = [role.value for role in capabilities.can_view_document_roles]
        statement = (
            select(PolicyDocumentVersion.id)
            .join(PolicyDocument, PolicyDocument.id == PolicyDocumentVersion.document_id)
            .join(PolicyAccessRule, PolicyAccessRule.document_id == PolicyDocument.id)
            .where(
                PolicyDocument.domain == domain.value,
                PolicyDocument.status == "published",
                PolicyDocument.effective_date <= today,
                or_(PolicyDocument.expires_at.is_(None), PolicyDocument.expires_at > today),
                PolicyDocumentVersion.is_active.is_(True),
                PolicyAccessRule.role.in_(role_values),
                PolicyAccessRule.region == user.region.upper(),
            )
        )
        return set(self.session.scalars(statement).all())

    def _reauthorize_candidate(
        self,
        *,
        chunk_id: UUID,
        expected_domain: Domain,
        expected_versions: set[UUID],
        user: UserContext,
        capabilities: CapabilitySet,
        score: float,
    ) -> AuthorizedChunk | None:
        result = self.session.execute(
            select(PolicyChunk, PolicyDocumentVersion, PolicyDocument)
            .join(PolicyDocumentVersion, PolicyDocumentVersion.id == PolicyChunk.document_version_id)
            .join(PolicyDocument, PolicyDocument.id == PolicyDocumentVersion.document_id)
            .where(PolicyChunk.id == chunk_id)
        ).one_or_none()
        if result is None:
            return None
        chunk, version, document = result
        if version.id not in expected_versions or document.domain != expected_domain.value:
            return None

        access_rules = self.session.scalars(
            select(PolicyAccessRule).where(PolicyAccessRule.document_id == document.id)
        ).all()
        try:
            document_roles = {Role(rule.role) for rule in access_rules}
        except ValueError:
            return None
        document_regions = {rule.region for rule in access_rules}
        decision = self.policy_enforcement.authorize_document(
            capabilities=capabilities,
            domain=expected_domain,
            document_status=document.status,
            effective_date=document.effective_date,
            expires_at=document.expires_at,
            document_roles=document_roles,
            document_regions=document_regions,
            user_region=user.region,
            today=date.today(),
        )
        if not decision.allowed:
            return None

        return AuthorizedChunk(
            chunk_id=chunk.id,
            document_version_id=version.id,
            domain=expected_domain,
            content=chunk.content,
            citation=CitationRef(
                document_id=document.document_id,
                title=document.title,
                version=version.version,
                section_id=chunk.section_id,
                effective_date=document.effective_date,
                excerpt=make_excerpt(chunk.content),
                score=score,
            ),
        )


def normalize_query(query: str) -> str:
    normalized = re.sub(r"\s+", " ", query).strip()
    if not normalized:
        raise ValueError("A policy search query is required.")
    if len(normalized) > 2_000:
        raise ValueError("Policy search query exceeds the allowed length.")
    return normalized


def make_excerpt(content: str, *, max_length: int = 500) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    return compact if len(compact) <= max_length else f"{compact[: max_length - 1].rstrip()}…"


def parse_uuid(value: object) -> UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
