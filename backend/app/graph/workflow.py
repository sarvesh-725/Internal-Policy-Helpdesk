import asyncio
from typing import Literal
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.domains.contracts import DomainFinding, DomainTaskEnvelope, HandoffEnvelope, PriorDomainFinding, RequestSensitivity, RouteIntent, RoutePlan
from app.domains.prompts import build_synthesis_prompt, build_triage_prompt
from app.graph.domain_subgraphs import build_domain_subgraph
from app.graph.state import GlobalSupportState
from app.config import get_settings
from app.llm.contracts import RequestMetadata
from app.llm.gemini_gateway import GeminiChatModelGateway
from app.persistence.database import SessionLocal
from app.persistence.models import MockReviewTask
from app.policy.enforcement import PolicyEnforcementPoint
from app.safety.contracts import GuardDecision, SafeRequestRepresentation
from app.safety.response_validator import ResponseSafetyValidator
from app.schemas import CitationRef, Domain, RedactedUserContext, ResponseStatus, SafeResponse, UserContext
from app.services.events import ThreadEventService
from app.services.review import ReviewTaskService
from app.tools.mock_adapters import MockReviewToolAdapter


DOMAIN_SUBGRAPHS = {domain: build_domain_subgraph(domain) for domain in Domain}
SPECIALIST_DOMAIN_PRIORITY = (Domain.HR, Domain.IT, Domain.OPERATIONS)


def build_support_graph(*, checkpointer):
    """Build a bounded hub-and-spoke graph; only the orchestrator selects graph edges."""
    builder = StateGraph(GlobalSupportState)
    builder.add_node("validate_request", validate_request)
    builder.add_node("guard_input", guard_input)
    builder.add_node("triage", triage)
    builder.add_node("clarify", clarify)
    builder.add_node("hr", make_domain_node(Domain.HR))
    builder.add_node("it", make_domain_node(Domain.IT))
    builder.add_node("operations", make_domain_node(Domain.OPERATIONS))
    builder.add_node("orchestrate_findings", orchestrate_findings)
    builder.add_node("validate_response", validate_response)
    builder.add_node("human_review", human_review)
    builder.add_node("respond", respond)
    builder.add_edge(START, "validate_request")
    builder.add_conditional_edges("validate_request", after_validation)
    builder.add_conditional_edges("guard_input", after_guard)
    builder.add_conditional_edges("triage", after_triage)
    builder.add_edge("clarify", "respond")
    builder.add_edge("hr", "orchestrate_findings")
    builder.add_edge("it", "orchestrate_findings")
    builder.add_edge("operations", "orchestrate_findings")
    builder.add_conditional_edges("orchestrate_findings", after_orchestration)
    builder.add_conditional_edges("validate_response", after_response_validation)
    builder.add_edge("human_review", "respond")
    builder.add_edge("respond", END)
    return builder.compile(checkpointer=checkpointer)


def validate_request(state: GlobalSupportState) -> dict:
    required = ("request_id", "thread_id", "user_context", "original_request_redacted", "guard_decision")
    if any(key not in state for key in required) or not state.get("request_id") or not state.get("thread_id") or not state.get("user_context"):
        return {"final_response": unavailable_response("invalid_workflow_request").model_dump(mode="json")}
    emit_progress(state, "identity_verified")
    return advance(state)


def guard_input(state: GlobalSupportState) -> dict:
    decision = GuardDecision(state["guard_decision"])
    if decision is GuardDecision.BLOCK:
        return {
            **advance(state),
            "final_response": SafeResponse(
                status=ResponseStatus.BLOCKED,
                message="Please do not share credentials, restricted identifiers, or other sensitive data in this support chat.",
                reason_code=state.get("guard_reason_code", "unsafe_request"),
            ).model_dump(mode="json"),
        }
    if decision is GuardDecision.ESCALATE:
        return {**advance(state), "escalation": escalation_state(state, reason_code=state.get("guard_reason_code", "guard_escalation"))}
    return advance(state)


def triage(state: GlobalSupportState) -> dict:
    if stop_for_limit(state):
        return {**advance(state), "escalation": escalation_state(state, reason_code="max_total_steps_exceeded")}
    user = user_from_state(state)
    emit_progress(state, "classifying_request")
    capabilities = PolicyEnforcementPoint().capabilities_for(user)
    safe_request = safe_request_from_state(state)
    try:
        plan = asyncio.run(
            GeminiChatModelGateway().structured(
                prompt=build_triage_prompt(request=safe_request, allowed_domains=capabilities.can_search_domains),
                schema=RoutePlan,
                metadata=metadata_from_state(state, user, "triage-v1"),
            )
        )
    except Exception:
        return {**advance(state), "escalation": escalation_state(state, reason_code="triage_model_unavailable")}
    outcome = deterministic_route(plan, capabilities.can_search_domains)
    return {**advance(state), "route_plan": plan.model_dump(mode="json"), **outcome}


def make_domain_node(domain: Domain):
    def run_domain(state: GlobalSupportState) -> dict:
        if stop_for_limit(state):
            return {**advance(state), "escalation": escalation_state(state, reason_code="max_total_steps_exceeded")}
        task = build_domain_task(state, domain)
        emit_progress(state, f"searching_authorized_{domain.value}_policy")
        local_result = DOMAIN_SUBGRAPHS[domain].invoke(
            {
                "task": task.model_dump(mode="json"),
                "finding": None,
                "error_code": None,
            }
        )
        if local_result.get("error_code"):
            return {
                **advance(state), "current_task": task.model_dump(mode="json"),
                "escalation": escalation_state(state, reason_code=str(local_result["error_code"]), required_domain=domain),
            }
        finding = DomainFinding.model_validate(local_result["finding"])
        findings = [*state.get("domain_findings", []), finding.model_dump(mode="json")]
        citations = [*state.get("citation_refs", []), *(citation.model_dump(mode="json") for citation in finding.citations)]
        return {**advance(state), "current_task": task.model_dump(mode="json"), "domain_findings": findings, "citation_refs": citations}

    return run_domain


def orchestrate_findings(state: GlobalSupportState) -> dict:
    pending = [Domain(value) for value in state.get("pending_domains", [])]
    completed = [Domain(value) for value in state.get("completed_domains", [])]
    if pending:
        current = pending.pop(0)
        completed.append(current)
    update: dict = {
        **advance(state),
        "pending_domains": [domain.value for domain in pending],
        "completed_domains": [domain.value for domain in completed],
        "domain_handoff_count": max(0, len(completed) - 1),
    }
    if update["domain_handoff_count"] > get_settings().max_domain_handoffs:
        update["escalation"] = escalation_state(state, reason_code="max_domain_handoffs_exceeded")
    return update


def validate_response(state: GlobalSupportState) -> dict:
    findings = [DomainFinding.model_validate(item) for item in state.get("domain_findings", [])]
    citations = deduplicate_citations([CitationRef.model_validate(item) for item in state.get("citation_refs", [])])
    if not findings or not citations:
        return {**advance(state), "escalation": escalation_state(state, reason_code="insufficient_authorized_evidence")}
    user = user_from_state(state)
    try:
        text = asyncio.run(
            GeminiChatModelGateway().generate(
                prompt=build_synthesis_prompt(safe_request=safe_request_from_state(state), findings=findings),
                metadata=metadata_from_state(state, user, "synthesis-v1"),
            )
        ).content
        ResponseSafetyValidator().validate_cited_response(message=text, citations=citations)
    except Exception:
        return {**advance(state), "final_response": unavailable_response("response_generation_unavailable").model_dump(mode="json")}
    emit_progress(state, "preparing_cited_response")
    return {
        **advance(state),
        "final_response": SafeResponse(
            status=ResponseStatus.COMPLETED,
            message=text,
            citations=citations,
            reason_code="authorized_cited_policy_response",
        ).model_dump(mode="json"),
    }


def clarify(state: GlobalSupportState) -> dict:
    """A deterministic clarification terminal: no model or data tool is invoked."""
    response = SafeResponse.model_validate(state["final_response"])
    emit_progress(state, "clarification_required", {"missing_fields": response.missing_fields})
    return {"final_response": response.model_dump(mode="json")}


def human_review(state: GlobalSupportState) -> dict:
    user = user_from_state(state)
    capabilities = PolicyEnforcementPoint().capabilities_for(user)
    review_authorization = PolicyEnforcementPoint().authorize_mock_review_creation(capabilities)
    if not review_authorization.allowed:
        return {
            "final_response": SafeResponse(
                status=ResponseStatus.ESCALATED,
                message="This request requires specialist handling through an authorized support channel.",
                reason_code=review_authorization.reason_code,
            ).model_dump(mode="json")
        }
    request_id = UUID(state["request_id"])
    thread_id = UUID(state["thread_id"])
    escalation = state.get("escalation", {})
    required_domain = Domain(escalation.get("required_domain", Domain.HR.value))
    with SessionLocal() as session:
        prior_task = session.scalar(select_task_by_request(request_id))
        task = MockReviewToolAdapter().create_mock_review_task(
            session,
            thread_id=thread_id,
            request_id=request_id,
            actor=user,
            capabilities=capabilities,
            required_domain=required_domain,
            safe_case_summary=review_case_summary(state),
            trace_id=state.get("trace_id"),
        )
        if prior_task is None:
            ThreadEventService().emit(
                session,
                thread_id=thread_id,
                request_id=request_id,
                event_type="awaiting_specialist_review",
                payload={"review_task_id": str(task.id)},
            )
        session.commit()
    resume_payload = interrupt({"review_task_id": str(task.id), "required_specialist_role": task.required_specialist_role})
    decision = str(resume_payload.get("decision", "")) if isinstance(resume_payload, dict) else ""
    edited = resume_payload.get("edited_response") if isinstance(resume_payload, dict) else None
    if decision == "reject":
        response = SafeResponse(
            status=ResponseStatus.REVIEW_REJECTED,
            message="A specialist reviewed this request and could not approve a policy response.",
            reason_code="review_rejected",
            review_task_id=task.id,
        )
    elif decision in {"approve", "edit"}:
        response_text = edited if isinstance(edited, str) and edited.strip() else "A specialist reviewed the request. Please follow the approved support process."
        try:
            ResponseSafetyValidator().validate_reviewer_response(
                message=response_text,
                citations=deduplicate_citations([CitationRef.model_validate(item) for item in state.get("citation_refs", [])]),
            )
        except Exception:
            response_text = "A specialist reviewed the request. Please follow the approved support process."
        response = SafeResponse(
            status=ResponseStatus.COMPLETED,
            message=response_text,
            citations=deduplicate_citations([CitationRef.model_validate(item) for item in state.get("citation_refs", [])]),
            reason_code="review_approved",
            review_task_id=task.id,
        )
    else:
        response = SafeResponse(
            status=ResponseStatus.ESCALATED,
            message="This request remains with a specialist for review.",
            reason_code="invalid_review_resume",
            review_task_id=task.id,
        )
    return {"review_task_id": str(task.id), "final_response": response.model_dump(mode="json")}


def respond(state: GlobalSupportState) -> dict:
    response = SafeResponse.model_validate(state.get("final_response") or unavailable_response("missing_final_response"))
    if state.get("request_id") and state.get("thread_id"):
        emit_progress(state, "completed", {"status": response.status.value})
    return {"final_response": response.model_dump(mode="json")}


def after_guard(state: GlobalSupportState) -> Literal["respond", "triage", "human_review"]:
    if state.get("final_response"):
        return "respond"
    if state.get("escalation"):
        return "human_review"
    return "triage"


def after_validation(state: GlobalSupportState) -> Literal["respond", "guard_input"]:
    return "respond" if state.get("final_response") else "guard_input"


def after_triage(state: GlobalSupportState) -> str:
    if state.get("final_response"):
        response = SafeResponse.model_validate(state["final_response"])
        return "clarify" if response.status is ResponseStatus.CLARIFICATION_REQUIRED else "respond"
    if state.get("escalation"):
        return "human_review"
    pending = state.get("pending_domains", [])
    return pending[0] if pending else "validate_response"


def after_orchestration(state: GlobalSupportState) -> str:
    if state.get("escalation"):
        return "human_review"
    pending = state.get("pending_domains", [])
    return pending[0] if pending else "validate_response"


def after_response_validation(state: GlobalSupportState) -> Literal["respond", "human_review"]:
    return "respond" if state.get("final_response") else "human_review"


def deterministic_route(plan: RoutePlan, allowed_domains: frozenset[Domain]) -> dict:
    if not set(plan.domains).issubset(allowed_domains):
        return {"escalation": {"reason_code": "requested_domain_not_authorized", "required_domain": Domain.HR.value}}
    if plan.missing_fields:
        return {
            "final_response": SafeResponse(
                status=ResponseStatus.CLARIFICATION_REQUIRED,
                message="Please provide the missing policy context without sharing sensitive personal information.",
                reason_code="missing_required_context",
                missing_fields=plan.missing_fields,
            ).model_dump(mode="json")
        }
    if (
        plan.intent is RouteIntent.ACTION_REQUEST
        or plan.requires_personal_record
        or plan.requires_human_review
        or plan.sensitivity is RequestSensitivity.RESTRICTED
    ):
        return {"escalation": {"reason_code": "specialist_review_required", "required_domain": select_review_domain(plan.domains).value}}
    return {"pending_domains": [domain.value for domain in plan.domains]}


def select_review_domain(domains: list[Domain]) -> Domain:
    return next((domain for domain in SPECIALIST_DOMAIN_PRIORITY if domain in domains), Domain.HR)


def escalation_state(state: GlobalSupportState, *, reason_code: str, required_domain: Domain | None = None) -> dict:
    route = state.get("route_plan", {})
    domains = [Domain(value) for value in route.get("domains", []) if value in {domain.value for domain in Domain}]
    return {"reason_code": reason_code, "required_domain": (required_domain or select_review_domain(domains)).value}


def advance(state: GlobalSupportState) -> dict:
    return {"total_step_count": int(state.get("total_step_count", 0)) + 1}


def stop_for_limit(state: GlobalSupportState) -> bool:
    return int(state.get("total_step_count", 0)) >= get_settings().max_total_steps


def user_from_state(state: GlobalSupportState) -> UserContext:
    return RedactedUserContext.model_validate(state["user_context"]).as_policy_user()


def safe_request_from_state(state: GlobalSupportState) -> SafeRequestRepresentation:
    return SafeRequestRepresentation(
        content=state["original_request_redacted"],
        decision=GuardDecision.ALLOW,
        risk_flags=tuple(state.get("risk_flags", [])),
        requires_human_review=False,
        signals=(),
        reason_code=state.get("guard_reason_code", "safe_request"),
    )


def metadata_from_state(state: GlobalSupportState, user: UserContext, prompt_version: str) -> RequestMetadata:
    return RequestMetadata(
        request_id=UUID(state["request_id"]),
        thread_id=UUID(state["thread_id"]),
        actor_subject_hash=user.subject_hash,
        prompt_version=prompt_version,
    )


def review_case_summary(state: GlobalSupportState) -> str:
    reason = state.get("escalation", {}).get("reason_code", "specialist_review_required")
    return f"Policy-support request requires specialist review. Reason: {reason}."


def build_domain_task(state: GlobalSupportState, target_domain: Domain) -> DomainTaskEnvelope:
    """Construct the only cross-domain handoff object; it deliberately excludes raw messages and local chunks."""
    completed = [Domain(value) for value in state.get("completed_domains", [])]
    findings = [DomainFinding.model_validate(item) for item in state.get("domain_findings", [])]
    prior = [
        PriorDomainFinding(
            domain=finding.domain,
            summary=finding.summary[:800],
            citation_ids=[citation_identifier(citation) for citation in finding.citations],
        )
        for finding in findings[-2:]
    ]
    handoff = HandoffEnvelope(
        request_id=state["request_id"],
        from_domain=completed[-1] if completed else None,
        to_domain=target_domain,
        safe_facts={"prior_domain_completed": bool(completed), "prior_domains": [domain.value for domain in completed]},
        prior_findings=prior,
    )
    return DomainTaskEnvelope(
        request_id=state["request_id"],
        thread_id=state["thread_id"],
        target_domain=target_domain,
        user_context=RedactedUserContext.model_validate(state["user_context"]),
        safe_subquestion=state["original_request_redacted"],
        handoff=handoff,
    )


def citation_identifier(citation: CitationRef) -> str:
    return f"{citation.document_id}@{citation.version}#{citation.section_id}"


def deduplicate_citations(citations: list[CitationRef]) -> list[CitationRef]:
    unique: dict[tuple[str, str, str], CitationRef] = {}
    for citation in citations:
        unique[(citation.document_id, citation.version, citation.section_id)] = citation
    return list(unique.values())[:12]


def unavailable_response(reason_code: str) -> SafeResponse:
    return SafeResponse(
        status=ResponseStatus.UNAVAILABLE,
        message="The policy-support service is temporarily unavailable. Please try again later or contact support.",
        reason_code=reason_code,
    )


def emit_progress(state: GlobalSupportState, event_type: str, payload: dict | None = None) -> None:
    with SessionLocal() as session:
        ThreadEventService().emit(
            session,
            thread_id=UUID(state["thread_id"]),
            request_id=UUID(state["request_id"]),
            event_type=event_type,
            payload=payload,
        )
        session.commit()


def select_task_by_request(request_id: UUID):
    from sqlalchemy import select

    return select(MockReviewTask).where(MockReviewTask.request_id == request_id).limit(1)
