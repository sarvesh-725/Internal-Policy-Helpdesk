from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import DemoEmployee, MockReviewTask
from app.audit.writer import AuditWriter
from app.policy.enforcement import PolicyEnforcementPoint
from app.schemas import CapabilitySet, Domain, ReviewDecision, Role, UserContext
from app.services.review import ReviewTaskService


class MockToolAuthorizationError(PermissionError):
    pass


class MockToolNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class DemoEmployeeContext:
    """Minimum synthetic self-context. No name, contact, pay, medical, or records are returned."""

    region: str
    department: str | None


class MockReviewToolAdapter:
    """The sole allowlisted interface for demo review-task creation, status, and resume."""

    def __init__(self, service: ReviewTaskService | None = None, policy: PolicyEnforcementPoint | None = None) -> None:
        self.service = service or ReviewTaskService()
        self.policy = policy or PolicyEnforcementPoint()
        self.audit_writer = AuditWriter()

    def create_mock_review_task(
        self,
        session: Session,
        *,
        thread_id: UUID,
        request_id: UUID,
        actor: UserContext,
        capabilities: CapabilitySet,
        required_domain: Domain,
        safe_case_summary: str,
        trace_id: str | None = None,
    ) -> MockReviewTask:
        decision = self.policy.authorize_mock_review_creation(capabilities)
        if not decision.allowed:
            raise MockToolAuthorizationError(decision.reason_code)
        return self.service.get_or_create(
            session,
            thread_id=thread_id,
            request_id=request_id,
            actor=actor,
            required_domain=required_domain,
            safe_case_summary=safe_case_summary,
            trace_id=trace_id,
        )

    def get_demo_case_status(self, session: Session, *, task_id: UUID, actor: UserContext) -> MockReviewTask:
        task = session.get(MockReviewTask, task_id)
        if task is None:
            raise MockToolNotFoundError("Mock review task does not exist.")
        is_owner = task.owner_subject_hash == actor.subject_hash
        is_matching_specialist = task.required_specialist_role in {role.value for role in actor.roles}
        if not is_owner and not is_matching_specialist:
            raise MockToolAuthorizationError("case_status_not_authorized")
        self.audit_writer.append(
            session,
            request_id=task.request_id,
            thread_id=task.thread_id,
            actor=actor,
            event_type="mock_case_status_read",
            resource_type="mock_review_task",
            resource_id=str(task.id),
            decision="allowed",
            reason_code="case_status_authorized",
            metadata={},
        )
        return task

    def resume_mock_review(
        self,
        session: Session,
        *,
        task_id: UUID,
        reviewer: UserContext,
        capabilities: CapabilitySet,
        decision: ReviewDecision,
        edited_response: str | None,
    ) -> MockReviewTask:
        return self.service.decide(
            session,
            task_id=task_id,
            reviewer=reviewer,
            capabilities=capabilities,
            decision=decision,
            edited_response=edited_response,
        )


class DemoEmployeeContextToolAdapter:
    """Returns synthetic, non-sensitive context for the authenticated person only."""

    def get_demo_employee_context(self, session: Session, *, request_id: UUID, actor: UserContext) -> DemoEmployeeContext:
        employee = session.scalar(select(DemoEmployee).where(DemoEmployee.keycloak_subject == actor.subject))
        result = DemoEmployeeContext(region=actor.region, department=None) if employee is None else DemoEmployeeContext(region=employee.region, department=employee.department)
        AuditWriter().append(
            session,
            request_id=request_id,
            actor=actor,
            event_type="demo_employee_context_read",
            resource_type="demo_employee",
            resource_id=actor.subject_hash,
            decision="allowed",
            reason_code="self_context_only",
            metadata={"department_available": bool(result.department)},
        )
        return result
