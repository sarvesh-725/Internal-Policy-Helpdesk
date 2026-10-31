from app.config import Settings, get_settings
from app.safety.contracts import DetectedSignal, GuardDecision, SafeRequestRepresentation, SensitivityClass
from app.safety.detectors import RawMatch, SignalDetector


class RequestGuard:
    """Redacts before graph/model access and makes escalation/blocking deterministic."""

    def __init__(self, settings: Settings | None = None, detector: SignalDetector | None = None) -> None:
        self.settings = settings or get_settings()
        self.detector = detector or SignalDetector(presidio_enabled=self.settings.presidio_enabled)

    def process(self, raw_content: str) -> SafeRequestRepresentation:
        if not isinstance(raw_content, str):
            return self._blocked("invalid_input_type")
        if not raw_content.strip():
            return self._blocked("empty_input")
        if len(raw_content) > self.settings.input_max_characters:
            return self._blocked("input_too_large")

        sensitive_matches = self.detector.find_sensitive_matches(raw_content)
        injection_signals = self.detector.find_injection_signals(raw_content)
        redacted_content = redact(raw_content, sensitive_matches)
        detected_signals = tuple(
            DetectedSignal(category=match.category, detector=match.detector, placeholder=match.placeholder)
            for match in sensitive_matches
        ) + tuple(injection_signals)

        categories = {match.category for match in sensitive_matches}
        if SensitivityClass.SECURITY_SENSITIVE in categories or SensitivityClass.RESTRICTED_IDENTIFIER in categories:
            return SafeRequestRepresentation(
                content=redacted_content,
                decision=GuardDecision.BLOCK,
                risk_flags=tuple(sorted(category.value for category in categories)),
                requires_human_review=False,
                signals=detected_signals,
                reason_code="restricted_or_security_sensitive_content",
            )
        if SensitivityClass.MEDICAL in categories or SensitivityClass.SENSITIVE_EMPLOYMENT in categories:
            return SafeRequestRepresentation(
                content="[REDACTED_SENSITIVE_REQUEST]",
                decision=GuardDecision.ESCALATE,
                risk_flags=tuple(sorted(category.value for category in categories)),
                requires_human_review=True,
                signals=detected_signals,
                reason_code="sensitive_personal_decision_required",
            )
        if injection_signals:
            return SafeRequestRepresentation(
                content=redacted_content,
                decision=GuardDecision.ESCALATE,
                risk_flags=(SensitivityClass.PROMPT_INJECTION.value,),
                requires_human_review=True,
                signals=detected_signals,
                reason_code="prompt_injection_signal",
            )
        return SafeRequestRepresentation(
            content=redacted_content,
            decision=GuardDecision.ALLOW,
            risk_flags=tuple(sorted(category.value for category in categories)),
            requires_human_review=False,
            signals=detected_signals,
            reason_code="safe_request",
        )

    @staticmethod
    def _blocked(reason_code: str) -> SafeRequestRepresentation:
        return SafeRequestRepresentation(
            content="",
            decision=GuardDecision.BLOCK,
            risk_flags=(reason_code,),
            requires_human_review=False,
            signals=(),
            reason_code=reason_code,
        )


def redact(text: str, matches: list[RawMatch]) -> str:
    redacted = text
    for match in sorted(matches, key=lambda item: item.start, reverse=True):
        redacted = f"{redacted[:match.start]}{match.placeholder}{redacted[match.end:]}"
    return redacted
