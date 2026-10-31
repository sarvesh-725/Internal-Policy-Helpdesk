"""Add policy-ingestion status records.

Revision ID: 20261031_0002
Revises: 20261031_0001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261031_0002"
down_revision = "20261031_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_ingestion_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_path", sa.String(500), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(120), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=True),
        sa.Column("detail", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_policy_ingestion_records_source_path", "policy_ingestion_records", ["source_path"])
    op.create_index("ix_policy_ingestion_records_source_hash", "policy_ingestion_records", ["source_hash"])
    op.create_index("ix_policy_ingestion_records_document_id", "policy_ingestion_records", ["document_id"])
    op.create_index("ix_policy_ingestion_records_status", "policy_ingestion_records", ["status"])


def downgrade() -> None:
    op.drop_table("policy_ingestion_records")
