"""Harden mock-review idempotency and audit privileges.

Revision ID: 20261031_0005
Revises: 20261031_0004
"""

from alembic import op


revision = "20261031_0005"
down_revision = "20261031_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_mock_review_task_request", "mock_review_tasks", ["request_id"])
    op.execute("REVOKE UPDATE, DELETE ON TABLE audit_events FROM nodeswarm_app")


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON TABLE audit_events TO nodeswarm_app")
    op.drop_constraint("uq_mock_review_task_request", "mock_review_tasks", type_="unique")
