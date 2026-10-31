from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DatabaseSession
from app.auth.dependencies import require_roles
from app.persistence.models import AuditEvent
from app.schemas import Role

router = APIRouter(prefix="/admin/audit-events", tags=["audit"])


@router.get("", dependencies=[Depends(require_roles(Role.SYSTEM_ADMIN))])
def list_audit_events(db: DatabaseSession, limit: int = 100) -> list[dict]:
    safe_limit = min(max(limit, 1), 200)
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(safe_limit)).all()
    return [
        {
            "event_id": str(event.event_id),
            "occurred_at": (event.occurred_at or datetime.now(timezone.utc)).isoformat(),
            "event_type": event.event_type,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "decision": event.decision,
            "reason_code": event.reason_code,
            "trace_id": event.trace_id,
            "redacted_metadata": event.redacted_metadata,
        }
        for event in events
    ]
