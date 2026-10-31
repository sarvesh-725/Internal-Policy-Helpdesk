from app.schemas import CapabilitySet, Domain, Role, UserContext


ROLE_DOMAIN_ACCESS: dict[Role, frozenset[Domain]] = {
    Role.EMPLOYEE: frozenset({Domain.HR, Domain.IT, Domain.OPERATIONS}),
    Role.MANAGER: frozenset({Domain.HR, Domain.IT}),
    Role.HR_SPECIALIST: frozenset({Domain.HR}),
    Role.IT_SPECIALIST: frozenset({Domain.IT}),
    Role.OPERATIONS_SPECIALIST: frozenset({Domain.OPERATIONS}),
    Role.POLICY_ADMIN: frozenset({Domain.HR, Domain.IT, Domain.OPERATIONS}),
    Role.SYSTEM_ADMIN: frozenset(),
}


def build_capabilities(user: UserContext) -> CapabilitySet:
    """Derive capabilities once from validated Keycloak claims; never from request input."""

    searchable_domains = frozenset().union(*(ROLE_DOMAIN_ACCESS[role] for role in user.roles))
    specialist_roles = {Role.HR_SPECIALIST, Role.IT_SPECIALIST, Role.OPERATIONS_SPECIALIST}

    return CapabilitySet(
        can_search_domains=searchable_domains,
        can_view_document_roles=user.roles,
        can_create_mock_review=bool(user.roles.intersection({Role.EMPLOYEE, Role.MANAGER})),
        can_resume_review=bool(user.roles.intersection(specialist_roles)),
        can_publish_policy=Role.POLICY_ADMIN in user.roles,
    )
