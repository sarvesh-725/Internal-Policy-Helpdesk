from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas import CitationRef, Domain, RedactedUserContext


class RouteIntent(StrEnum):
    POLICY_QUESTION = "policy_question"
    STATUS_QUESTION = "status_question"
    ACTION_REQUEST = "action_request"
    UNKNOWN = "unknown"


class RequestSensitivity(StrEnum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    RESTRICTED = "restricted"


class RoutePlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    domains: list[Domain] = Field(min_length=1, max_length=3)
    intent: RouteIntent
    sensitivity: RequestSensitivity
    requires_personal_record: bool
    requires_human_review: bool
    missing_fields: list[str] = Field(default_factory=list, max_length=3)
    reason_code: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def use_unique_domains(self) -> "RoutePlan":
        if len(set(self.domains)) != len(self.domains):
            raise ValueError("Route domains must be unique.")
        return self


class DomainFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain: Domain
    summary: str = Field(min_length=1, max_length=2_000)
    policy_facts: list[str] = Field(min_length=1, max_length=6)
    citations: list[CitationRef] = Field(min_length=1, max_length=4)
    requires_human_review: bool
    reason_code: str = Field(min_length=1, max_length=100)


class PriorDomainFinding(BaseModel):
    """A citation-preserving, short finding permitted in a cross-domain handoff."""

    model_config = ConfigDict(frozen=True)

    domain: Domain
    summary: str = Field(min_length=1, max_length=800)
    citation_ids: list[str] = Field(min_length=1, max_length=4)


class HandoffEnvelope(BaseModel):
    """Minimum-necessary information passed from one completed domain to another."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    from_domain: Domain | None
    to_domain: Domain
    safe_facts: dict[str, str | bool | list[str]] = Field(default_factory=dict)
    prior_findings: list[PriorDomainFinding] = Field(default_factory=list, max_length=2)
    constraints: dict[str, bool] = Field(
        default_factory=lambda: {
            "must_cite_authorized_policy": True,
            "must_escalate_personal_outcome": True,
            "do_not_request_personal_records": True,
        }
    )


class DomainTaskEnvelope(BaseModel):
    """The complete, capability-narrow input to an HR, IT, or Operations subgraph."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    thread_id: str
    target_domain: Domain
    user_context: RedactedUserContext
    safe_subquestion: str = Field(min_length=1, max_length=2_000)
    handoff: HandoffEnvelope
