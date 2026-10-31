import hashlib
import json
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.persistence.models import AuditEvent
from app.observability.setup import current_trace_id
from app.schemas import UserContext


class AuditWriter:
    """Writes tamper-evident, category-only audit records in the caller's transaction."""

    _ADVISORY_LOCK_ID = 911_204_061

    def append(
        self,
        session: Session,
        *,
        request_id: UUID,
        actor: UserContext,
        event_type: str,
        decision: str,
        reason_code: str | None = None,
        thread_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        trace_id: str | None = None,
        metadata: dict[str, str | int | bool | list[str]] | None = None,
    ) -> AuditEvent:
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": self._ADVISORY_LOCK_ID})
        trace_id = trace_id or current_trace_id()
        previous = session.scalar(select(AuditEvent).order_by(AuditEvent.occurred_at.desc(), AuditEvent.event_id.desc()).limit(1))
        redacted_metadata = metadata or {}
        canonical_event = {
            "request_id": str(request_id),
            "thread_id": str(thread_id) if thread_id else None,
            "actor_subject_hash": actor.subject_hash,
            "actor_roles": sorted(role.value for role in actor.roles),
            "event_type": event_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "decision": decision,
            "reason_code": reason_code,
            "trace_id": trace_id,
            "previous_event_hash": previous.event_hash if previous else None,
            "redacted_metadata": redacted_metadata,
        }
        event_hash = hashlib.sha256(json.dumps(canonical_event, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        event = AuditEvent(
            request_id=request_id,
            thread_id=thread_id,
            actor_subject_hash=actor.subject_hash,
            actor_roles=sorted(role.value for role in actor.roles),
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            decision=decision,
            reason_code=reason_code,
            trace_id=trace_id,
            previous_event_hash=previous.event_hash if previous else None,
            event_hash=event_hash,
            redacted_metadata=redacted_metadata,
        )
        session.add(event)
        return event
