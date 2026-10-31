from app.safety.contracts import SensitivityClass
from app.safety.detectors import SignalDetector
from app.schemas import CitationRef


class ResponseValidationError(ValueError):
    pass


class ResponseSafetyValidator:
    """Final deterministic boundary before model/reviewer prose becomes user-visible."""

    def __init__(self) -> None:
        self.detector = SignalDetector(presidio_enabled=False)

    def validate_cited_response(self, *, message: str, citations: list[CitationRef]) -> None:
        if not message.strip():
            raise ResponseValidationError("Response is empty.")
        if not citations:
            raise ResponseValidationError("A policy response must have authorized citations.")
        self._validate_text(message)

    def validate_reviewer_response(self, *, message: str, citations: list[CitationRef]) -> None:
        if not message.strip():
            raise ResponseValidationError("Reviewer response is empty.")
        self._validate_text(message)
        if contains_policy_claim(message) and not citations:
            raise ResponseValidationError("A reviewer policy claim requires an authorized citation.")

    def _validate_text(self, message: str) -> None:
        matches = self.detector.find_sensitive_matches(message)
        unsafe_categories = {match.category for match in matches}
        if unsafe_categories.intersection(
            {SensitivityClass.RESTRICTED_IDENTIFIER, SensitivityClass.SECURITY_SENSITIVE, SensitivityClass.MEDICAL}
        ):
            raise ResponseValidationError("Response contains restricted or sensitive data.")


def contains_policy_claim(message: str) -> bool:
    policy_markers = ("policy", "must ", "eligible", "leave", "access", "workflow", "approval")
    normalized = f" {message.lower()} "
    return any(marker in normalized for marker in policy_markers)
