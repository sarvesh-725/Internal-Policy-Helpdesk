import hashlib
from collections.abc import Callable
from typing import Any

from fastapi import Depends, Header

from app.auth.jwt_validator import TokenValidationError, validate_access_token
from app.schemas import Role, UserContext


class AuthenticationError(Exception):
    pass


class AuthorizationError(Exception):
    pass


def get_current_user(authorization: str | None = Header(default=None)) -> UserContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError()

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AuthenticationError()

    try:
        claims = validate_access_token(token)
    except TokenValidationError as exc:
        raise AuthenticationError() from exc
    return map_claims_to_user_context(claims)


def map_claims_to_user_context(claims: dict[str, Any]) -> UserContext:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AuthenticationError()

    known_roles = {role.value: role for role in Role}
    realm_access = claims.get("realm_access") if isinstance(claims.get("realm_access"), dict) else {}
    raw_roles = set(realm_access.get("roles", []))
    resource_access = claims.get("resource_access") if isinstance(claims.get("resource_access"), dict) else {}
    for client_claims in resource_access.values():
        if isinstance(client_claims, dict):
            raw_roles.update(client_claims.get("roles", []))
    roles = frozenset(known_roles[role] for role in raw_roles if role in known_roles)
    if not roles:
        raise AuthorizationError()

    region = claims.get("region")
    if not isinstance(region, str) or not region:
        attributes = claims.get("attributes", {})
        region_values = attributes.get("region", []) if isinstance(attributes, dict) else []
        region = region_values[0] if region_values else "US"

    return UserContext(
        subject=subject,
        subject_hash=hashlib.sha256(subject.encode("utf-8")).hexdigest(),
        username=claims.get("preferred_username") if isinstance(claims.get("preferred_username"), str) else None,
        roles=roles,
        region=region.upper(),
    )


def require_roles(*required_roles: Role) -> Callable[[UserContext], UserContext]:
    def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        if not user.roles.intersection(required_roles):
            raise AuthorizationError()
        return user

    return dependency
