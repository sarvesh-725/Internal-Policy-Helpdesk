from uuid import uuid4

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DatabaseSession
from app.audit.writer import AuditWriter
from app.persistence.models import ConversationThread, FeedbackEvent
from app.schemas import FeedbackCreate

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=204)
def create_feedback(body: FeedbackCreate, user: CurrentUser, db: DatabaseSession) -> None:
    thread = db.scalar(select(ConversationThread).where(ConversationThread.id == body.thread_id, ConversationThread.owner_subject_hash == user.subject_hash))
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found.")
    db.add(FeedbackEvent(thread_id=thread.id, owner_subject_hash=user.subject_hash, helpful=body.helpful, category=body.category))
    AuditWriter().append(
        db,
        request_id=uuid4(),
        thread_id=thread.id,
        actor=user,
        event_type="feedback_recorded",
        decision="allowed",
        resource_type="conversation_thread",
        resource_id=str(thread.id),
        metadata={"helpful": body.helpful, "category_provided": bool(body.category)},
    )
    db.commit()
