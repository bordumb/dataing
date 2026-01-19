"""JWT authentication middleware."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dataing.core.auth.jwt import TokenError, decode_token
from dataing.core.auth.types import OrgRole

logger = structlog.get_logger()

# Use Bearer token authentication
bearer_scheme = HTTPBearer(auto_error=False)

# Role hierarchy - higher index = more permissions
ROLE_HIERARCHY = [OrgRole.VIEWER, OrgRole.MEMBER, OrgRole.ADMIN, OrgRole.OWNER]


@dataclass
class JwtContext:
    """Context from a verified JWT token."""

    user_id: str
    org_id: str
    role: OrgRole
    teams: list[str]

    @property
    def user_uuid(self) -> UUID:
        """Get user ID as UUID."""
        return UUID(self.user_id)

    @property
    def org_uuid(self) -> UUID:
        """Get org ID as UUID."""
        return UUID(self.org_id)


async def verify_jwt(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),  # noqa: B008
) -> JwtContext:
    """Verify JWT token and return context.

    This dependency validates the JWT and returns user/org context.

    Args:
        request: The current request.
        credentials: Bearer token credentials.

    Returns:
        JwtContext with user info.

    Raises:
        HTTPException: 401 if token is missing or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
    except TokenError as e:
        logger.warning(f"jwt_validation_failed: {e}")
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    context = JwtContext(
        user_id=payload.sub,
        org_id=payload.org_id,
        role=OrgRole(payload.role),
        teams=payload.teams,
    )

    # Store in request state for downstream use
    request.state.user = context

    logger.debug(
        f"jwt_verified: user_id={context.user_id}, "
        f"org_id={context.org_id}, role={context.role.value}"
    )

    return context


def require_role(min_role: OrgRole) -> Callable[..., Any]:
    """Dependency to require a minimum role level.

    Role hierarchy (lowest to highest):
    - viewer: read-only access
    - member: can create/modify own resources
    - admin: can manage team resources
    - owner: full control including billing/settings

    Usage:
        @router.delete("/{id}")
        async def delete_item(
            auth: Annotated[JwtContext, Depends(require_role(OrgRole.ADMIN))],
        ):
            ...

    Args:
        min_role: Minimum required role.

    Returns:
        Dependency function that validates role.
    """

    async def role_checker(
        auth: Annotated[JwtContext, Depends(verify_jwt)],
    ) -> JwtContext:
        user_role_idx = ROLE_HIERARCHY.index(auth.role)
        required_role_idx = ROLE_HIERARCHY.index(min_role)

        if user_role_idx < required_role_idx:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{min_role.value}' or higher required",
            )
        return auth

    return role_checker


# Common role dependencies for convenience
RequireViewer = Annotated[JwtContext, Depends(require_role(OrgRole.VIEWER))]
RequireMember = Annotated[JwtContext, Depends(require_role(OrgRole.MEMBER))]
RequireAdmin = Annotated[JwtContext, Depends(require_role(OrgRole.ADMIN))]
RequireOwner = Annotated[JwtContext, Depends(require_role(OrgRole.OWNER))]


# Optional JWT - returns None if no token provided
async def optional_jwt(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),  # noqa: B008
) -> JwtContext | None:
    """Optionally verify JWT, returning None if not provided."""
    if not credentials:
        return None

    try:
        return await verify_jwt(request, credentials)
    except HTTPException:
        return None
