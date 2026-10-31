import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import ConversationThread, PolicyDocument


class PolicyRepository:
    """Persistence boundary for policy metadata; vector operations belong in Qdrant services."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_external_id(self, document_id: str) -> PolicyDocument | None:
        statement = select(PolicyDocument).where(PolicyDocument.document_id == document_id)
        return self.session.scalar(statement)


class ThreadRepository:
    """Persistence boundary for redacted conversation-thread records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_owned_thread(self, thread_id: uuid.UUID, owner_subject_hash: str) -> ConversationThread | None:
        statement = select(ConversationThread).where(
            ConversationThread.id == thread_id,
            ConversationThread.owner_subject_hash == owner_subject_hash,
        )
        return self.session.scalar(statement)
