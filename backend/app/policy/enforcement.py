from dataclasses import dataclass
from datetime import date

from app.policy.capabilities import build_capabilities
from app.schemas import CapabilitySet, Domain, Role, UserContext


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_code: str


class PolicyEnforcementPoint:
    """Server-side authorization boundary used by retrieval and future mock tools."""

    def capabilities_for(self, user: UserContext) -> CapabilitySet:
        return build_capabilities(user)

    def authorize_domain_search(self, capabilities: CapabilitySet, domain: Domain) -> PolicyDecision:
        if domain not in capabilities.can_search_domains:
            return PolicyDecision(False, "domain_not_authorized")
        return PolicyDecision(True, "domain_authorized")

    def authorize_document(
        self,
        *,
        capabilities: CapabilitySet,
        domain: Domain,
        document_status: str,
        effective_date: date,
        expires_at: date | None,
        document_roles: set[Role],
        document_regions: set[str],
        user_region: str,
        today: date,
    ) -> PolicyDecision:
        domain_decision = self.authorize_domain_search(capabilities, domain)
        if not domain_decision.allowed:
            return domain_decision
        if document_status != "published":
            return PolicyDecision(False, "document_not_published")
        if effective_date > today:
            return PolicyDecision(False, "document_not_effective")
        if expires_at is not None and expires_at <= today:
            return PolicyDecision(False, "document_expired")
        if not capabilities.can_view_document_roles.intersection(document_roles):
            return PolicyDecision(False, "document_role_not_authorized")
        if user_region.upper() not in {region.upper() for region in document_regions}:
            return PolicyDecision(False, "document_region_not_authorized")
        return PolicyDecision(True, "document_authorized")

    def authorize_mock_review_creation(self, capabilities: CapabilitySet) -> PolicyDecision:
        if not capabilities.can_create_mock_review:
            return PolicyDecision(False, "review_creation_not_authorized")
        return PolicyDecision(True, "review_creation_authorized")

    def authorize_review_resume(self, capabilities: CapabilitySet, required_role: Role) -> PolicyDecision:
        if not capabilities.can_resume_review or required_role not in capabilities.can_view_document_roles:
            return PolicyDecision(False, "review_resume_not_authorized")
        return PolicyDecision(True, "review_resume_authorized")
