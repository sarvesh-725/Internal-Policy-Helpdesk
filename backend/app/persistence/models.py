import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.database import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampedModel:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PolicyDocument(TimestampedModel, Base):
    __tablename__ = "policy_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    domain: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    owner_role: Mapped[str] = mapped_column(String(80))
    source_path: Mapped[str] = mapped_column(String(500), unique=True)
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    effective_date: Mapped[date] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class PolicyDocumentVersion(TimestampedModel, Base):
    __tablename__ = "policy_document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_policy_document_version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_documents.id"), index=True)
    version: Mapped[str] = mapped_column(String(40))
    review_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PolicyAccessRule(TimestampedModel, Base):
    __tablename__ = "policy_access_rules"
    __table_args__ = (UniqueConstraint("document_id", "role", "region", name="uq_policy_access_rule"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_documents.id"), index=True)
    role: Mapped[str] = mapped_column(String(80), index=True)
    region: Mapped[str] = mapped_column(String(40), index=True)


class PolicyChunk(TimestampedModel, Base):
    __tablename__ = "policy_chunks"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_document_versions.id"), index=True)
    section_id: Mapped[str] = mapped_column(String(120))
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)


class PolicyIngestionRecord(TimestampedModel, Base):
    __tablename__ = "policy_ingestion_records"

    id: Mapped[uuid.UUID] = uuid_pk()
    source_path: Mapped[str] = mapped_column(String(500), index=True)
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    document_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DemoEmployee(TimestampedModel, Base):
    __tablename__ = "employees_demo"

    id: Mapped[uuid.UUID] = uuid_pk()
    keycloak_subject: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    region: Mapped[str] = mapped_column(String(40), index=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ConversationThread(TimestampedModel, Base):
    __tablename__ = "conversation_threads"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_subject_hash: Mapped[str] = mapped_column(String(64), index=True)
    safe_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)


class ConversationMessage(TimestampedModel, Base):
    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation_threads.id"), index=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(index=True, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(30))
    content_redacted: Mapped[str] = mapped_column(Text)
    citation_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (UniqueConstraint("request_id", "actor_type", name="uq_conversation_message_request_actor"),)


class MockReviewTask(TimestampedModel, Base):
    __tablename__ = "mock_review_tasks"

    id: Mapped[uuid.UUID] = uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation_threads.id"), index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(index=True)
    owner_subject_hash: Mapped[str] = mapped_column(String(64), index=True)
    required_specialist_role: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    safe_case_summary: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewer_subject_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    edited_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ThreadEvent(TimestampedModel, Base):
    __tablename__ = "thread_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation_threads.id"), index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    safe_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class GraphCheckpoint(TimestampedModel, Base):
    __tablename__ = "graph_checkpoints"

    id: Mapped[uuid.UUID] = uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation_threads.id"), index=True)
    checkpoint_key: Mapped[str] = mapped_column(String(160), unique=True)
    state_redacted: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(index=True)
    thread_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversation_threads.id"), nullable=True, index=True)
    actor_subject_hash: Mapped[str] = mapped_column(String(64), index=True)
    actor_roles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision: Mapped[str] = mapped_column(String(40), index=True)
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    previous_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)
    redacted_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class FeedbackEvent(TimestampedModel, Base):
    __tablename__ = "feedback_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation_threads.id"), index=True)
    owner_subject_hash: Mapped[str] = mapped_column(String(64), index=True)
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
