"""Add specialist decision fields and safe SSE event persistence.

Revision ID: 20261031_0003
Revises: 20261031_0002
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261031_0003"
down_revision = "20261031_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mock_review_tasks", sa.Column("reviewer_subject_hash", sa.String(64), nullable=True))
    op.add_column("mock_review_tasks", sa.Column("reviewer_role", sa.String(80), nullable=True))
    op.add_column("mock_review_tasks", sa.Column("decision", sa.String(30), nullable=True))
    op.add_column("mock_review_tasks", sa.Column("edited_response", sa.Text(), nullable=True))
    op.add_column("mock_review_tasks", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "thread_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("safe_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"]),
    )
    op.create_index("ix_thread_events_thread_id", "thread_events", ["thread_id"])
    op.create_index("ix_thread_events_request_id", "thread_events", ["request_id"])
    op.create_index("ix_thread_events_event_type", "thread_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("thread_events")
    op.drop_column("mock_review_tasks", "decided_at")
    op.drop_column("mock_review_tasks", "edited_response")
    op.drop_column("mock_review_tasks", "decision")
    op.drop_column("mock_review_tasks", "reviewer_role")
    op.drop_column("mock_review_tasks", "reviewer_subject_hash")
