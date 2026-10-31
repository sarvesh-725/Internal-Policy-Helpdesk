import re
from dataclasses import dataclass

from app.safety.contracts import DetectedSignal, SensitivityClass

try:
    from presidio_analyzer import AnalyzerEngine
except ImportError:  # The deterministic controls remain available before optional NLP dependencies are installed.
    AnalyzerEngine = None


@dataclass(frozen=True)
class RawMatch:
    start: int
    end: int
    category: SensitivityClass
    detector: str
    placeholder: str


_PATTERNS: tuple[tuple[SensitivityClass, str, re.Pattern[str], str], ...] = (
    (
        SensitivityClass.PERSONAL_IDENTIFIER,
        "email_pattern",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        SensitivityClass.PERSONAL_IDENTIFIER,
        "phone_pattern",
        re.compile(r"\b(?:\+?\d{1,3}[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}\b"),
        "[REDACTED_PHONE]",
    ),
    (
        SensitivityClass.RESTRICTED_IDENTIFIER,
        "ssn_pattern",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED_SSN]",
    ),
    (
        SensitivityClass.RESTRICTED_IDENTIFIER,
        "credit_card_pattern",
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        "[REDACTED_PAYMENT_IDENTIFIER]",
    ),
    (
        SensitivityClass.SECURITY_SENSITIVE,
        "api_key_pattern",
        re.compile(r"\b(?:AIza[\w-]{20,}|sk-[\w-]{16,}|ghp_[A-Za-z0-9]{20,})\b"),
        "[REDACTED_SECRET]",
    ),
    (
        SensitivityClass.SECURITY_SENSITIVE,
        "credential_assignment_pattern",
        re.compile(r"(?i)\b(?:password|passcode|access[_ -]?token|refresh[_ -]?token)\s*[:=]\s*\S+"),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        SensitivityClass.SENSITIVE_EMPLOYMENT,
        "employment_record_pattern",
        re.compile(r"(?i)\b(?:my|their)\s+(?:salary|compensation|performance review|disciplinary record|grant number)\b"),
        "[REDACTED_SENSITIVE_EMPLOYMENT_DETAIL]",
    ),
    (
        SensitivityClass.MEDICAL,
        "medical_detail_pattern",
        re.compile(r"(?i)\b(?:diagnosis|treatment plan|doctor(?:'s)? note|medical record|prescription|symptoms)\b"),
        "[REDACTED_MEDICAL_DETAIL]",
    ),
)

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|system|developer)\s+instructions\b"),
    re.compile(r"(?i)\b(?:reveal|show|print|repeat)\s+(?:the\s+)?(?:system|developer|hidden)\s+prompt\b"),
    re.compile(r"(?i)\b(?:bypass|disable|override)\s+(?:security|guardrails|rbac|authorization)\b"),
    re.compile(r"(?i)\bact\s+as\s+(?:the\s+)?(?:system|developer)\b"),
)


class SignalDetector:
    """Combines deterministic patterns with optional local Presidio identifier detection."""

    def __init__(self, *, presidio_enabled: bool) -> None:
        self._presidio = None
        if presidio_enabled and AnalyzerEngine is not None:
            try:
                self._presidio = AnalyzerEngine()
            except Exception:
                # The deterministic detector still prevents restricted values reaching a model.
                self._presidio = None

    def find_sensitive_matches(self, text: str) -> list[RawMatch]:
        matches = [
            RawMatch(match.start(), match.end(), category, detector, placeholder)
            for category, detector, pattern, placeholder in _PATTERNS
            for match in pattern.finditer(text)
        ]
        matches.extend(self._presidio_matches(text))
        return deduplicate_overlaps(matches)

    def find_injection_signals(self, text: str) -> list[DetectedSignal]:
        return [
            DetectedSignal(category=SensitivityClass.PROMPT_INJECTION, detector="injection_pattern")
            for pattern in _INJECTION_PATTERNS
            if pattern.search(text)
        ]

    def _presidio_matches(self, text: str) -> list[RawMatch]:
        if self._presidio is None:
            return []
        entity_map = {
            "EMAIL_ADDRESS": (SensitivityClass.PERSONAL_IDENTIFIER, "[REDACTED_EMAIL]"),
            "PHONE_NUMBER": (SensitivityClass.PERSONAL_IDENTIFIER, "[REDACTED_PHONE]"),
            "PERSON": (SensitivityClass.PERSONAL_IDENTIFIER, "[REDACTED_NAME]"),
            "US_SSN": (SensitivityClass.RESTRICTED_IDENTIFIER, "[REDACTED_SSN]"),
            "CREDIT_CARD": (SensitivityClass.RESTRICTED_IDENTIFIER, "[REDACTED_PAYMENT_IDENTIFIER]"),
        }
        results = self._presidio.analyze(text=text, language="en", entities=list(entity_map))
        return [
            RawMatch(result.start, result.end, entity_map[result.entity_type][0], f"presidio_{result.entity_type.lower()}", entity_map[result.entity_type][1])
            for result in results
            if result.entity_type in entity_map
        ]


def deduplicate_overlaps(matches: list[RawMatch]) -> list[RawMatch]:
    priority = {
        SensitivityClass.SECURITY_SENSITIVE: 0,
        SensitivityClass.RESTRICTED_IDENTIFIER: 1,
        SensitivityClass.MEDICAL: 2,
        SensitivityClass.SENSITIVE_EMPLOYMENT: 3,
        SensitivityClass.PERSONAL_IDENTIFIER: 4,
    }
    accepted: list[RawMatch] = []
    for candidate in sorted(matches, key=lambda item: (item.start, priority[item.category], -(item.end - item.start))):
        if any(candidate.start < existing.end and candidate.end > existing.start for existing in accepted):
            continue
        accepted.append(candidate)
    return accepted
