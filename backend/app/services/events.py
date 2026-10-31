from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.persistence.models import ThreadEvent
from app.schemas import ThreadEventResponse


class ThreadEventService:
    """Stores only allowlisted user-safe workflow projections for SSE clients."""

    SAFE_EVENT_TYPES = frozenset(
        {
            "request_received",
            "identity_verified",
            "classifying_request",
            "clarification_required",
            "searching_authorized_hr_policy",
            "searching_authorized_it_policy",
            "searching_authorized_operations_policy",
            "preparing_cited_response",
            "awaiting_specialist_review",
            "review_decision_recorded",
            "completed",
        }
    )

    def emit(self, session: Session, *, thread_id: UUID, request_id: UUID, event_type: str, payload: dict | None = None) -> None:
        if event_type not in self.SAFE_EVENT_TYPES:
            raise ValueError("Event type is not approved for browser streaming.")
        session.add(
            ThreadEvent(
                thread_id=thread_id,
                request_id=request_id,
                event_type=event_type,
                safe_payload=self._normalize_payload(event_type, payload or {}),
            )
        )

    def list_for_thread(self, session: Session, *, thread_id: UUID, after_event_id: UUID | None = None) -> list[ThreadEventResponse]:
        statement = select(ThreadEvent).where(ThreadEvent.thread_id == thread_id).order_by(ThreadEvent.created_at, ThreadEvent.id)
        if after_event_id is not None:
            anchor = session.scalar(select(ThreadEvent).where(ThreadEvent.id == after_event_id, ThreadEvent.thread_id == thread_id))
            if anchor is not None and anchor.created_at is not None:
                statement = statement.where(
                    or_(
                        ThreadEvent.created_at > anchor.created_at,
                        and_(ThreadEvent.created_at == anchor.created_at, ThreadEvent.id > anchor.id),
                    )
                )
        return [
            ThreadEventResponse(
                id=event.id,
                request_id=event.request_id,
                event_type=event.event_type,
                payload=event.safe_payload,
                occurred_at=event.created_at or datetime.now(timezone.utc),
            )
            for event in session.scalars(statement)
        ]

    @staticmethod
    def _normalize_payload(event_type: str, payload: dict) -> dict:
        if event_type == "awaiting_specialist_review":
            task_id = payload.get("review_task_id")
            return {"review_task_id": str(task_id)} if task_id else {}
        if event_type == "review_decision_recorded":
            decision = payload.get("decision")
            return {"decision": decision} if decision in {"approve", "reject", "edit"} else {}
        if event_type == "clarification_required":
            fields = payload.get("missing_fields", [])
            if not isinstance(fields, list):
                fields = []
            return {"missing_fields": [str(field)[:80] for field in fields[:3]]}
        if event_type == "completed":
            status = payload.get("status")
            allowed_statuses = {"completed", "clarification_required", "awaiting_review", "escalated", "blocked", "review_rejected", "unavailable"}
            return {"status": status} if status in allowed_statuses else {}
        return {}
