from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.writer import AuditWriter
from app.persistence.models import MockReviewTask
from app.policy.enforcement import PolicyEnforcementPoint
from app.safety.contracts import GuardDecision
from app.safety.guard import RequestGuard
from app.safety.response_validator import contains_policy_claim
from app.schemas import CapabilitySet, Domain, ReviewDecision, ReviewTaskResponse, Role, UserContext


SPECIALIST_FOR_DOMAIN: dict[Domain, Role] = {
    Domain.HR: Role.HR_SPECIALIST,
    Domain.IT: Role.IT_SPECIALIST,
    Domain.OPERATIONS: Role.OPERATIONS_SPECIALIST,
}


class ReviewTaskService:
    """Mock review lifecycle; it never connects to real enterprise action systems."""

    def __init__(self, policy_enforcement: PolicyEnforcementPoint | None = None, audit_writer: AuditWriter | None = None) -> None:
        self.policy_enforcement = policy_enforcement or PolicyEnforcementPoint()
        self.audit_writer = audit_writer or AuditWriter()

    def get_or_create(
        self,
        session: Session,
        *,
        thread_id: UUID,
        request_id: UUID,
        actor: UserContext,
        required_domain: Domain,
        safe_case_summary: str,
        trace_id: str | None = None,
    ) -> MockReviewTask:
        existing = session.scalar(select(MockReviewTask).where(MockReviewTask.request_id == request_id).limit(1))
        if existing is not None:
            return existing
        task = MockReviewTask(
            thread_id=thread_id,
            request_id=request_id,
            owner_subject_hash=actor.subject_hash,
            required_specialist_role=SPECIALIST_FOR_DOMAIN[required_domain].value,
            safe_case_summary=safe_case_summary[:2_000],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        session.add(task)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(select(MockReviewTask).where(MockReviewTask.request_id == request_id).limit(1))
            if existing is not None:
                return existing
            raise
        self.audit_writer.append(
            session,
            request_id=request_id,
            thread_id=thread_id,
            actor=actor,
            event_type="review_task_created",
            resource_type="mock_review_task",
            resource_id=str(task.id),
            decision="escalated",
            reason_code="human_review_required",
            trace_id=trace_id,
            metadata={"required_specialist_role": task.required_specialist_role},
        )
        return task

    def list_for_reviewer(self, session: Session, reviewer: UserContext) -> list[ReviewTaskResponse]:
        role_values = [role.value for role in reviewer.roles]
        statement = (
            select(MockReviewTask)
            .where(
                MockReviewTask.required_specialist_role.in_(role_values),
                MockReviewTask.status == "pending",
                MockReviewTask.expires_at > datetime.now(timezone.utc),
            )
            .order_by(MockReviewTask.created_at.desc())
        )
        return [self._to_response(task) for task in session.scalars(statement)]

    def decide(
        self,
        session: Session,
        *,
        task_id: UUID,
        reviewer: UserContext,
        capabilities: CapabilitySet,
        decision: ReviewDecision,
        edited_response: str | None,
    ) -> MockReviewTask:
        task = session.scalar(select(MockReviewTask).where(MockReviewTask.id == task_id).with_for_update())
        if task is None:
            raise LookupError("Review task does not exist.")
        if task.status != "pending":
            same_decision = (
                task.reviewer_subject_hash == reviewer.subject_hash
                and task.decision == decision.value
                and (decision is not ReviewDecision.EDIT or task.edited_response == (edited_response or "").strip())
            )
            if same_decision:
                return task
            raise ValueError("Review task is not pending.")
        if task.expires_at <= datetime.now(timezone.utc):
            task.status = "expired"
            session.commit()
            raise ValueError("Review task has expired.")
        required_role = Role(task.required_specialist_role)
        authorization = self.policy_enforcement.authorize_review_resume(capabilities, required_role)
        if not authorization.allowed:
            raise PermissionError(authorization.reason_code)
        safe_edited_response = self._safe_reviewer_response(decision, edited_response)
        task.status = "approved" if decision in {ReviewDecision.APPROVE, ReviewDecision.EDIT} else "rejected"
        task.reviewer_subject_hash = reviewer.subject_hash
        task.reviewer_role = required_role.value
        task.decision = decision.value
        task.edited_response = safe_edited_response
        task.decided_at = datetime.now(timezone.utc)
        self.audit_writer.append(
            session,
            request_id=task.request_id,
            thread_id=task.thread_id,
            actor=reviewer,
            event_type="review_task_decided",
            resource_type="mock_review_task",
            resource_id=str(task.id),
            decision=task.status,
            reason_code="reviewer_decision",
            metadata={"reviewer_role": required_role.value, "decision": decision.value, "has_edited_response": bool(safe_edited_response)},
        )
        session.commit()
        return task

    @staticmethod
    def _to_response(task: MockReviewTask) -> ReviewTaskResponse:
        return ReviewTaskResponse(
            task_id=task.id,
            thread_id=task.thread_id,
            status=task.status,
            required_specialist_role=Role(task.required_specialist_role),
            safe_case_summary=task.safe_case_summary,
            expires_at=task.expires_at,
        )

    @staticmethod
    def _safe_reviewer_response(decision: ReviewDecision, value: str | None) -> str | None:
        if decision is not ReviewDecision.EDIT:
            return None
        if not value or not value.strip():
            raise ValueError("An edited response is required for an edit decision.")
        guarded = RequestGuard().process(value)
        if guarded.decision is not GuardDecision.ALLOW:
            raise ValueError("The edited response contains unsafe content.")
        if contains_policy_claim(guarded.content):
            raise ValueError("Reviewer edits may provide process status only; policy claims require the cited graph response.")
        return guarded.content
