from typing import NotRequired
from typing_extensions import TypedDict


class GlobalSupportState(TypedDict):
    """JSON-serializable graph state only; no raw input, JWTs, tools, or chain of thought."""

    request_id: str
    thread_id: str
    user_context: dict
    original_request_redacted: str
    guard_decision: str
    risk_flags: list[str]
    guard_reason_code: str
    trace_id: NotRequired[str]
    route_plan: NotRequired[dict]
    pending_domains: NotRequired[list[str]]
    completed_domains: NotRequired[list[str]]
    domain_handoff_count: NotRequired[int]
    total_step_count: NotRequired[int]
    domain_findings: NotRequired[list[dict]]
    citation_refs: NotRequired[list[dict]]
    current_task: NotRequired[dict]
    escalation: NotRequired[dict]
    final_response: NotRequired[dict]
    review_task_id: NotRequired[str]
