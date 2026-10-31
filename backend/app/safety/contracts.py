from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GuardDecision(StrEnum):
    ALLOW = "allow"
    ESCALATE = "escalate"
    BLOCK = "block"


class SensitivityClass(StrEnum):
    PERSONAL_IDENTIFIER = "personal_identifier"
    RESTRICTED_IDENTIFIER = "restricted_identifier"
    SENSITIVE_EMPLOYMENT = "sensitive_employment"
    MEDICAL = "medical"
    SECURITY_SENSITIVE = "security_sensitive"
    PROMPT_INJECTION = "prompt_injection"


class DetectedSignal(BaseModel):
    """A category-only finding. Raw matches and offsets intentionally never escape the detector."""

    model_config = ConfigDict(frozen=True)

    category: SensitivityClass
    detector: str
    placeholder: str | None = None


class SafeRequestRepresentation(BaseModel):
    """The only request content allowed into graph state, model prompts, traces, and audit metadata."""

    model_config = ConfigDict(frozen=True)

    content: str = Field(max_length=8_000)
    decision: GuardDecision
    risk_flags: tuple[str, ...]
    requires_human_review: bool
    signals: tuple[DetectedSignal, ...]
    reason_code: str
