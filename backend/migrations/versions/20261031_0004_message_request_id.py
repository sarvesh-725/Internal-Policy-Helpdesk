"""Associate redacted messages with graph requests for idempotent completion.

Revision ID: 20261031_0004
Revises: 20261031_0003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261031_0004"
down_revision = "20261031_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversation_messages", sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_conversation_messages_request_id", "conversation_messages", ["request_id"])
    op.create_unique_constraint("uq_conversation_message_request_actor", "conversation_messages", ["request_id", "actor_type"])


def downgrade() -> None:
    op.drop_constraint("uq_conversation_message_request_actor", "conversation_messages", type_="unique")
    op.drop_index("ix_conversation_messages_request_id", table_name="conversation_messages")
    op.drop_column("conversation_messages", "request_id")
