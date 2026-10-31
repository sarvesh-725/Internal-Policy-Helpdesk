"""Create the initial NodeSwarm relational schema.

Revision ID: 20261031_0001
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261031_0001"
down_revision = None
branch_labels = None
depends_on = None


def uuid_column(name: str, *, primary_key: bool = False, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), primary_key=primary_key, nullable=nullable)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "policy_documents",
        uuid_column("id", primary_key=True),
        sa.Column("document_id", sa.String(120), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("domain", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("owner_role", sa.String(80), nullable=False),
        sa.Column("source_path", sa.String(500), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("document_id"),
        sa.UniqueConstraint("source_path"),
    )
    op.create_index("ix_policy_documents_document_id", "policy_documents", ["document_id"])
    op.create_index("ix_policy_documents_domain", "policy_documents", ["domain"])
    op.create_index("ix_policy_documents_status", "policy_documents", ["status"])
    op.create_index("ix_policy_documents_source_hash", "policy_documents", ["source_hash"])

    op.create_table(
        "policy_document_versions",
        uuid_column("id", primary_key=True),
        uuid_column("document_id"),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("review_due_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.ForeignKeyConstraint(["document_id"], ["policy_documents.id"]),
        sa.UniqueConstraint("document_id", "version", name="uq_policy_document_version"),
    )
    op.create_index("ix_policy_document_versions_document_id", "policy_document_versions", ["document_id"])

    op.create_table(
        "policy_access_rules",
        uuid_column("id", primary_key=True),
        uuid_column("document_id"),
        sa.Column("role", sa.String(80), nullable=False),
        sa.Column("region", sa.String(40), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["document_id"], ["policy_documents.id"]),
        sa.UniqueConstraint("document_id", "role", "region", name="uq_policy_access_rule"),
    )
    op.create_index("ix_policy_access_rules_document_id", "policy_access_rules", ["document_id"])
    op.create_index("ix_policy_access_rules_role", "policy_access_rules", ["role"])
    op.create_index("ix_policy_access_rules_region", "policy_access_rules", ["region"])

    op.create_table(
        "policy_chunks",
        uuid_column("id", primary_key=True),
        uuid_column("document_version_id"),
        sa.Column("section_id", sa.String(120), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("qdrant_point_id", sa.String(120), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["document_version_id"], ["policy_document_versions.id"]),
        sa.UniqueConstraint("qdrant_point_id"),
    )
    op.create_index("ix_policy_chunks_document_version_id", "policy_chunks", ["document_version_id"])
    op.create_index("ix_policy_chunks_content_hash", "policy_chunks", ["content_hash"])

    op.create_table(
        "employees_demo",
        uuid_column("id", primary_key=True),
        sa.Column("keycloak_subject", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("region", sa.String(40), nullable=False),
        sa.Column("department", sa.String(120), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("keycloak_subject"),
    )
    op.create_index("ix_employees_demo_keycloak_subject", "employees_demo", ["keycloak_subject"])
    op.create_index("ix_employees_demo_region", "employees_demo", ["region"])

    op.create_table(
        "conversation_threads",
        uuid_column("id", primary_key=True),
        sa.Column("owner_subject_hash", sa.String(64), nullable=False),
        sa.Column("safe_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="active"),
        *timestamps(),
    )
    op.create_index("ix_conversation_threads_owner_subject_hash", "conversation_threads", ["owner_subject_hash"])

    op.create_table(
        "conversation_messages",
        uuid_column("id", primary_key=True),
        uuid_column("thread_id"),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("content_redacted", sa.Text(), nullable=False),
        sa.Column("citation_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *timestamps(),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"]),
    )
    op.create_index("ix_conversation_messages_thread_id", "conversation_messages", ["thread_id"])

    op.create_table(
        "mock_review_tasks",
        uuid_column("id", primary_key=True),
        uuid_column("thread_id"),
        uuid_column("request_id"),
        sa.Column("owner_subject_hash", sa.String(64), nullable=False),
        sa.Column("required_specialist_role", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("safe_case_summary", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"]),
    )
    op.create_index("ix_mock_review_tasks_thread_id", "mock_review_tasks", ["thread_id"])
    op.create_index("ix_mock_review_tasks_request_id", "mock_review_tasks", ["request_id"])
    op.create_index("ix_mock_review_tasks_owner_subject_hash", "mock_review_tasks", ["owner_subject_hash"])
    op.create_index("ix_mock_review_tasks_required_specialist_role", "mock_review_tasks", ["required_specialist_role"])
    op.create_index("ix_mock_review_tasks_status", "mock_review_tasks", ["status"])

    op.create_table(
        "graph_checkpoints",
        uuid_column("id", primary_key=True),
        uuid_column("thread_id"),
        sa.Column("checkpoint_key", sa.String(160), nullable=False),
        sa.Column("state_redacted", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *timestamps(),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"]),
        sa.UniqueConstraint("checkpoint_key"),
    )
    op.create_index("ix_graph_checkpoints_thread_id", "graph_checkpoints", ["thread_id"])

    op.create_table(
        "audit_events",
        uuid_column("event_id", primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        uuid_column("request_id"),
        uuid_column("thread_id", nullable=True),
        sa.Column("actor_subject_hash", sa.String(64), nullable=False),
        sa.Column("actor_roles", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=True),
        sa.Column("trace_id", sa.String(100), nullable=True),
        sa.Column("previous_event_hash", sa.String(64), nullable=True),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("redacted_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"]),
        sa.UniqueConstraint("event_hash"),
    )
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_thread_id", "audit_events", ["thread_id"])
    op.create_index("ix_audit_events_actor_subject_hash", "audit_events", ["actor_subject_hash"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_decision", "audit_events", ["decision"])

    op.create_table(
        "feedback_events",
        uuid_column("id", primary_key=True),
        uuid_column("thread_id"),
        sa.Column("owner_subject_hash", sa.String(64), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"]),
    )
    op.create_index("ix_feedback_events_thread_id", "feedback_events", ["thread_id"])
    op.create_index("ix_feedback_events_owner_subject_hash", "feedback_events", ["owner_subject_hash"])


def downgrade() -> None:
    for table_name in [
        "feedback_events", "audit_events", "graph_checkpoints", "mock_review_tasks", "conversation_messages",
        "conversation_threads", "employees_demo", "policy_chunks", "policy_access_rules", "policy_document_versions",
        "policy_documents",
    ]:
        op.drop_table(table_name)
