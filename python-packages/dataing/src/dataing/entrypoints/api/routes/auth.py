"""Auth API routes for login, registration, and token refresh."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from dataing.adapters.audit import record_audit, suppress_audit_errors
from dataing.adapters.auth.postgres import PostgresAuthRepository
from dataing.core.auth.recovery import PasswordRecoveryAdapter
from dataing.core.auth.service import AuthError, AuthService
from dataing.core.auth.types import User
from dataing.entrypoints.api.deps import get_frontend_url, get_recovery_adapter
from dataing.entrypoints.api.middleware.jwt_auth import JwtContext, verify_jwt

router = APIRouter(tags=["auth"])


# Request/Response models
class LoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr
    password: str
    org_id: UUID


class RegisterRequest(BaseModel):
    """Registration request body."""

    email: EmailStr
    password: str
    name: str
    org_name: str
    org_slug: str | None = None


class RefreshRequest(BaseModel):
    """Token refresh request body."""

    refresh_token: str
    org_id: UUID


class TokenResponse(BaseModel):
    """Token response."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: dict[str, Any] | None = None
    org: dict[str, Any] | None = None
    role: str | None = None


class PasswordResetRequest(BaseModel):
    """Password reset request body."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation body."""

    token: str
    new_password: str = Field(..., min_length=8)


class RecoveryMethodResponse(BaseModel):
    """Recovery method response."""

    type: str
    message: str
    action_url: str | None = None
    admin_email: str | None = None


def get_auth_service(request: Request) -> AuthService:
    """Get auth service from request context."""
    app_db = request.app.state.app_db
    repo = PostgresAuthRepository(app_db)
    return AuthService(repo)


# These routes run before any auth context exists, so @audited can't cover
# them; they record their events explicitly.


async def _record_user_event(
    http_request: Request,
    action: str,
    tenant_id: UUID,
    email: str,
    *,
    user_id: UUID | None = None,
    actor_id: UUID | None = None,
    status_code: int = 200,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an auth event about the user account behind `email`.

    actor_email names that account even when the caller hasn't proven they own
    it (failed logins, reset requests); actor_id is set only once they have.
    """
    await record_audit(
        http_request,
        action=action,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_email=email,
        resource_type="user",
        resource_id=user_id,
        resource_name=email,
        status_code=status_code,
        metadata=metadata,
    )


async def _record_token_event(
    http_request: Request, action: str, result: dict[str, Any], status_code: int = 200
) -> None:
    """Record a login or registration under the org it was for."""
    with suppress_audit_errors(action):
        user_id = UUID(result["user"]["id"])
        await _record_user_event(
            http_request,
            action,
            UUID(result["org"]["id"]),
            result["user"]["email"],
            user_id=user_id,
            actor_id=user_id,
            status_code=status_code,
        )


async def _record_in_user_orgs(
    http_request: Request,
    service: AuthService,
    action: str,
    user: User,
    actor_id: UUID | None,
) -> None:
    """Record a password reset event in every org the user belongs to."""
    with suppress_audit_errors(action):
        for org_id in await service.get_user_org_ids(user.id):
            await _record_user_event(
                http_request, action, org_id, user.email, user_id=user.id, actor_id=actor_id
            )


@router.post("/login", response_model=TokenResponse)
async def login(
    http_request: Request,
    body: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Authenticate user and return tokens.

    Args:
        http_request: HTTP request, for audit logging.
        body: Login credentials.
        service: Auth service.

    Returns:
        Access and refresh tokens with user/org info.
    """
    try:
        result = await service.login(
            email=body.email,
            password=body.password,
            org_id=body.org_id,
        )
    except AuthError as e:
        with suppress_audit_errors("auth.login_failed"):
            # Callers choose org_id: only record under an org that exists, so
            # nobody can create audit rows under made-up tenant IDs.
            if await service.org_exists(body.org_id):
                await _record_user_event(
                    http_request,
                    "auth.login_failed",
                    body.org_id,
                    body.email,
                    status_code=401,
                    metadata={"reason": str(e)},
                )
        raise HTTPException(status_code=401, detail=str(e)) from None

    await _record_token_event(http_request, "auth.login", result)
    return TokenResponse(**result)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    http_request: Request,
    body: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Register new user and create organization.

    Args:
        http_request: HTTP request, for audit logging.
        body: Registration info.
        service: Auth service.

    Returns:
        Access and refresh tokens with user/org info.
    """
    try:
        result = await service.register(
            email=body.email,
            password=body.password,
            name=body.name,
            org_name=body.org_name,
            org_slug=body.org_slug,
        )
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    await _record_token_event(http_request, "auth.register", result, status_code=201)
    return TokenResponse(**result)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Refresh access token.

    Args:
        body: Refresh token and org ID.
        service: Auth service.

    Returns:
        New access token.
    """
    try:
        result = await service.refresh(
            refresh_token=body.refresh_token,
            org_id=body.org_id,
        )
        return TokenResponse(**result)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None


@router.get("/me")
async def get_current_user(
    auth: Annotated[JwtContext, Depends(verify_jwt)],
) -> dict[str, Any]:
    """Get current authenticated user info."""
    return {
        "user_id": auth.user_id,
        "org_id": auth.org_id,
        "role": auth.role.value,
        "teams": auth.teams,
    }


@router.get("/me/orgs")
async def get_user_orgs(
    auth: Annotated[JwtContext, Depends(verify_jwt)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> list[dict[str, Any]]:
    """Get all organizations the current user belongs to.

    Returns list of orgs with role for each.
    """
    orgs: list[dict[str, Any]] = await service.get_user_orgs(auth.user_uuid)
    return orgs


# Password reset endpoints


@router.post("/password-reset/recovery-method", response_model=RecoveryMethodResponse)
async def get_recovery_method(
    body: PasswordResetRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    recovery_adapter: Annotated[PasswordRecoveryAdapter, Depends(get_recovery_adapter)],
) -> RecoveryMethodResponse:
    """Get the recovery method for a user's email.

    This tells the frontend what UI to show (email form, admin contact, etc.).

    Args:
        body: Request containing the user's email.
        service: Auth service.
        recovery_adapter: Password recovery adapter.

    Returns:
        Recovery method describing how the user can reset their password.
    """
    method = await service.get_recovery_method(body.email, recovery_adapter)
    return RecoveryMethodResponse(
        type=method.type,
        message=method.message,
        action_url=method.action_url,
        admin_email=method.admin_email,
    )


@router.post("/password-reset/request")
async def request_password_reset(
    http_request: Request,
    body: PasswordResetRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    recovery_adapter: Annotated[PasswordRecoveryAdapter, Depends(get_recovery_adapter)],
    frontend_url: Annotated[str, Depends(get_frontend_url)],
) -> dict[str, str]:
    """Request a password reset.

    For security, this always returns success regardless of whether
    the email exists. This prevents email enumeration attacks.

    The actual recovery method depends on the configured adapter:
    - email: Sends reset link via email
    - console: Prints reset link to server console (demo/dev mode)
    - admin_contact: Logs the request for admin visibility

    Args:
        http_request: HTTP request, for audit logging.
        body: Request containing the user's email.
        service: Auth service.
        recovery_adapter: Password recovery adapter.
        frontend_url: Frontend URL for building reset links.

    Returns:
        Success message.
    """
    # Always succeeds (for security - doesn't reveal if email exists)
    user = await service.request_password_reset(
        email=body.email,
        recovery_adapter=recovery_adapter,
        frontend_url=frontend_url,
    )
    if user is not None:
        # Anyone can request a reset for any email, so it isn't attributed to the user
        await _record_in_user_orgs(
            http_request, service, "auth.password_reset_request", user, actor_id=None
        )

    return {"message": "If an account with that email exists, we've sent a password reset link."}


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    http_request: Request,
    body: PasswordResetConfirm,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    """Reset password using a valid token.

    Args:
        http_request: HTTP request, for audit logging.
        body: Request containing the reset token and new password.
        service: Auth service.

    Returns:
        Success message.

    Raises:
        HTTPException: If token is invalid, expired, or already used.
    """
    try:
        user = await service.reset_password(
            token=body.token,
            new_password=body.new_password,
        )
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    await _record_in_user_orgs(
        http_request, service, "auth.password_reset_complete", user, actor_id=user.id
    )
    return {"message": "Password has been reset successfully."}
