from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Domain(StrEnum):
    HR = "hr"
    IT = "it"
    OPERATIONS = "operations"


class Role(StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    HR_SPECIALIST = "hr_specialist"
    IT_SPECIALIST = "it_specialist"
    OPERATIONS_SPECIALIST = "operations_specialist"
    POLICY_ADMIN = "policy_admin"
    SYSTEM_ADMIN = "system_admin"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


class ResponseStatus(StrEnum):
    COMPLETED = "completed"
    CLARIFICATION_REQUIRED = "clarification_required"
    AWAITING_REVIEW = "awaiting_review"
    ESCALATED = "escalated"
    BLOCKED = "blocked"
    REVIEW_REJECTED = "review_rejected"
    UNAVAILABLE = "unavailable"


class UserContext(BaseModel):
    """Trusted request-scoped identity derived only from a validated Keycloak token."""

    model_config = ConfigDict(frozen=True)

    subject: str
    subject_hash: str
    username: str | None = None
    roles: frozenset[Role]
    region: str


class RedactedUserContext(BaseModel):
    """The identity representation allowed into workflow state and domain handoffs."""

    model_config = ConfigDict(frozen=True)

    subject_hash: str
    roles: frozenset[Role]
    region: str

    @classmethod
    def from_user(cls, user: UserContext) -> "RedactedUserContext":
        return cls(subject_hash=user.subject_hash, roles=user.roles, region=user.region)

    def as_policy_user(self) -> UserContext:
        """Adapts to legacy policy interfaces without reconstructing the original Keycloak subject."""
        return UserContext(subject=f"hash:{self.subject_hash}", subject_hash=self.subject_hash, roles=self.roles, region=self.region)


class CapabilitySet(BaseModel):
    """Immutable least-privilege permissions derived from trusted identity."""

    model_config = ConfigDict(frozen=True)

    can_search_domains: frozenset[Domain]
    can_view_document_roles: frozenset[Role]
    can_create_mock_review: bool = False
    can_resume_review: bool = False
    can_publish_policy: bool = False
    can_execute_real_write: bool = False


class ApiError(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class MetaResponse(BaseModel):
    name: str
    environment: str
    api_version: str
    llm_provider: str
    vector_store: str = "qdrant"


class HealthResponse(BaseModel):
    status: str = "ok"


class ReadinessResponse(BaseModel):
    status: str = "ready"


class CurrentUserResponse(BaseModel):
    subject: str
    username: str | None
    roles: list[Role]
    region: str


class CitationRef(BaseModel):
    document_id: str
    title: str
    version: str
    section_id: str
    effective_date: date | None = None
    excerpt: str
    score: float | None = None


class AuthorizedChunk(BaseModel):
    chunk_id: UUID
    document_version_id: UUID
    domain: Domain
    content: str
    citation: CitationRef


class SafeResponse(BaseModel):
    """User-visible output only; never carry hidden prompts, tools, diagnostics, or raw input."""

    model_config = ConfigDict(frozen=True)

    status: ResponseStatus
    message: str = Field(min_length=1, max_length=8_000)
    citations: list[CitationRef] = Field(default_factory=list, max_length=12)
    reason_code: str = Field(min_length=1, max_length=100)
    review_task_id: UUID | None = None
    missing_fields: list[str] = Field(default_factory=list, max_length=3)


class ThreadCreateResponse(BaseModel):
    thread_id: UUID
    status: str


class GraphRunAcceptedResponse(BaseModel):
    thread_id: UUID
    request_id: UUID
    status: str


class ThreadEventResponse(BaseModel):
    id: UUID
    request_id: UUID
    event_type: str
    payload: dict
    occurred_at: datetime


class ThreadMessageResponse(BaseModel):
    id: UUID
    actor_type: str
    content: str
    citations: list[CitationRef] = Field(default_factory=list)
    occurred_at: datetime


class ThreadReviewStatusResponse(BaseModel):
    task_id: UUID
    status: str
    expires_at: datetime
    required_specialist_role: Role


class ThreadDetailResponse(BaseModel):
    thread_id: UUID
    status: str
    messages: list[ThreadMessageResponse]
    review_status: ThreadReviewStatusResponse | None = None


class ReviewTaskResponse(BaseModel):
    task_id: UUID
    thread_id: UUID
    status: str
    required_specialist_role: Role
    safe_case_summary: str
    expires_at: datetime


class PolicyIngestResponse(BaseModel):
    ingested: int
    quarantined: int
    entries: list[dict[str, str]]


class ChatThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=160)


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8_000)


class ReviewDecisionCreate(BaseModel):
    decision: ReviewDecision
    edited_response: str | None = Field(default=None, max_length=8_000)


class FeedbackCreate(BaseModel):
    thread_id: UUID
    helpful: bool
    category: str | None = Field(default=None, max_length=100)


class SseProgressEvent(BaseModel):
    event: str
    request_id: UUID
    occurred_at: datetime
