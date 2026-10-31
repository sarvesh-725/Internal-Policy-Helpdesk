from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.config import get_settings


class TokenValidationError(Exception):
    """Raised when a bearer token cannot become trusted application identity."""


@lru_cache
def jwks_client() -> PyJWKClient:
    return PyJWKClient(get_settings().keycloak_jwks_url, cache_jwk_set=True, lifespan=300)


def validate_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        signing_key = jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.keycloak_audience,
            issuer=settings.keycloak_issuer_url,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenValidationError("Invalid bearer token") from exc
