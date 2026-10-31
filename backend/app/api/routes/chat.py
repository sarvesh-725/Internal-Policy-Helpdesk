import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DatabaseSession
from app.audit.writer import AuditWriter
from app.graph.runner import SupportGraphRunner
from app.observability.setup import current_trace_id
from app.persistence.models import ConversationMessage, ConversationThread, MockReviewTask
from app.safety.guard import RequestGuard
from app.schemas import RedactedUserContext
from app.schemas import ChatMessageCreate, ChatThreadCreate, GraphRunAcceptedResponse, Role, ThreadCreateResponse, ThreadDetailResponse, ThreadMessageResponse, ThreadReviewStatusResponse
from app.services.events import ThreadEventService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/threads", response_model=ThreadCreateResponse, status_code=201)
def create_thread(_: ChatThreadCreate, user: CurrentUser, db: DatabaseSession) -> ThreadCreateResponse:
    thread = ConversationThread(owner_subject_hash=user.subject_hash)
    db.add(thread)
    db.flush()
    AuditWriter().append(db, request_id=uuid4(), thread_id=thread.id, actor=user, event_type="thread_created", decision="allowed", resource_type="conversation_thread", resource_id=str(thread.id), metadata={})
    db.commit()
    return ThreadCreateResponse(thread_id=thread.id, status=thread.status)


@router.post("/threads/{thread_id}/messages", response_model=GraphRunAcceptedResponse, status_code=202)
def create_message(thread_id: UUID, body: ChatMessageCreate, background_tasks: BackgroundTasks, user: CurrentUser, db: DatabaseSession) -> GraphRunAcceptedResponse:
    thread = _owned_thread(db, thread_id, user.subject_hash, lock=True)
    if thread.status in {"processing", "awaiting_review"}:
        raise HTTPException(status_code=409, detail="This thread already has an active request.")
    guarded = RequestGuard().process(body.content)
    request_id = uuid4()
    db.add(ConversationMessage(thread_id=thread.id, request_id=request_id, actor_type="user", content_redacted=guarded.content or "[BLOCKED_REQUEST]", citation_metadata={}))
    thread.status = "processing"
    ThreadEventService().emit(db, thread_id=thread.id, request_id=request_id, event_type="request_received", payload={})
    AuditWriter().append(
        db, request_id=request_id, thread_id=thread.id, actor=user, event_type="request_guard_processed", decision=guarded.decision.value,
        reason_code=guarded.reason_code, resource_type="conversation_thread", resource_id=str(thread.id),
        metadata={"risk_flags": list(guarded.risk_flags), "signal_categories": [signal.category.value for signal in guarded.signals]},
    )
    db.commit()
    initial_state = {
        "request_id": str(request_id), "thread_id": str(thread.id), "user_context": RedactedUserContext.from_user(user).model_dump(mode="json"),
        "original_request_redacted": guarded.content, "guard_decision": guarded.decision.value,
        "trace_id": current_trace_id(),
        "risk_flags": list(guarded.risk_flags), "guard_reason_code": guarded.reason_code, "completed_domains": [],
        "domain_handoff_count": 0, "total_step_count": 0, "domain_findings": [], "citation_refs": [],
    }
    background_tasks.add_task(SupportGraphRunner().run, initial_state)
    return GraphRunAcceptedResponse(thread_id=thread.id, request_id=request_id, status="processing")


@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
def get_thread(thread_id: UUID, user: CurrentUser, db: DatabaseSession) -> ThreadDetailResponse:
    thread = _owned_thread(db, thread_id, user.subject_hash)
    messages = db.scalars(select(ConversationMessage).where(ConversationMessage.thread_id == thread.id).order_by(ConversationMessage.created_at)).all()
    latest_review = db.scalar(
        select(MockReviewTask)
        .where(MockReviewTask.thread_id == thread.id, MockReviewTask.owner_subject_hash == user.subject_hash)
        .order_by(MockReviewTask.created_at.desc())
        .limit(1)
    )
    return ThreadDetailResponse(
        thread_id=thread.id, status=thread.status,
        messages=[ThreadMessageResponse(id=message.id, actor_type=message.actor_type, content=message.content_redacted, citations=message.citation_metadata.get("citations", []), occurred_at=message.created_at or datetime.now(timezone.utc)) for message in messages],
        review_status=(
            ThreadReviewStatusResponse(
                task_id=latest_review.id,
                status=latest_review.status,
                expires_at=latest_review.expires_at,
                required_specialist_role=Role(latest_review.required_specialist_role),
            )
            if latest_review is not None
            else None
        ),
    )


@router.get("/threads/{thread_id}/events")
async def stream_events(thread_id: UUID, user: CurrentUser, db: DatabaseSession, last_event_id: str | None = Header(default=None)) -> StreamingResponse:
    _owned_thread(db, thread_id, user.subject_hash)
    # The streaming generator uses its own short-lived sessions; do not retain this request session for five minutes.
    db.close()
    try:
        cursor = UUID(last_event_id) if last_event_id else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid event cursor.") from exc

    async def event_stream():
        after = cursor
        for _ in range(300):
            from app.persistence.database import SessionLocal
            with SessionLocal() as session:
                current_thread = _owned_thread(session, thread_id, user.subject_hash)
                events = ThreadEventService().list_for_thread(session, thread_id=thread_id, after_event_id=after)
                for event in events:
                    after = event.id
                    data = {"request_id": str(event.request_id), "payload": event.payload, "occurred_at": event.occurred_at.isoformat()}
                    yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(data)}\n\n"
                if current_thread.status not in {"processing", "awaiting_review"}:
                    break
            yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def _owned_thread(db, thread_id: UUID, subject_hash: str, lock: bool = False) -> ConversationThread:
    statement = select(ConversationThread).where(ConversationThread.id == thread_id, ConversationThread.owner_subject_hash == subject_hash)
    if lock:
        statement = statement.with_for_update()
    thread = db.scalar(statement)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found.")
    return thread
