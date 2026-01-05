"""API middleware."""

from dataing.entrypoints.api.middleware.audit import AuditMiddleware
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    optional_api_key,
    require_scope,
    verify_api_key,
)
from dataing.entrypoints.api.middleware.jwt_auth import (
    JwtContext,
    RequireAdmin,
    RequireMember,
    RequireOwner,
    RequireViewer,
    optional_jwt,
    require_role,
    verify_jwt,
)
from dataing.entrypoints.api.middleware.rate_limit import RateLimitMiddleware

__all__ = [
    # API Key auth
    "ApiKeyContext",
    "verify_api_key",
    "require_scope",
    "optional_api_key",
    # JWT auth
    "JwtContext",
    "verify_jwt",
    "require_role",
    "optional_jwt",
    "RequireViewer",
    "RequireMember",
    "RequireAdmin",
    "RequireOwner",
    # Middleware
    "RateLimitMiddleware",
    "AuditMiddleware",
]
