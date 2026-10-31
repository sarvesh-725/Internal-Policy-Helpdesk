from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DatabaseSession
from app.audit.writer import AuditWriter
from app.auth.dependencies import require_roles
from app.retrieval.ingestion import PolicyIngestionService, PolicySourceError
from app.schemas import PolicyIngestResponse, Role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/policies/ingest", response_model=PolicyIngestResponse, dependencies=[Depends(require_roles(Role.POLICY_ADMIN))])
def ingest_policies(user: CurrentUser, db: DatabaseSession) -> PolicyIngestResponse:
    try:
        report = PolicyIngestionService(db).ingest_all()
    except PolicySourceError as exc:
        raise HTTPException(status_code=422, detail="The policy corpus could not be ingested.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Policy ingestion is temporarily unavailable.") from exc
    AuditWriter().append(
        db,
        request_id=uuid4(),
        actor=user,
        event_type="policy_ingestion_requested",
        decision="completed",
        reason_code="ingestion_report_available",
        resource_type="policy_corpus",
        metadata={"ingested": report.ingested, "quarantined": report.quarantined},
    )
    db.commit()
    return PolicyIngestResponse(ingested=report.ingested, quarantined=report.quarantined, entries=report.entries)
