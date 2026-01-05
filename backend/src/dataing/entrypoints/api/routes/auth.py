"""Auth API routes for login, registration, and token refresh."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from dataing.adapters.auth.postgres import PostgresAuthRepository
from dataing.core.auth.recovery import PasswordRecoveryAdapter
from dataing.core.auth.service import AuthError, AuthService
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


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Authenticate user and return tokens.

    Args:
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
        return TokenResponse(**result)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Register new user and create organization.

    Args:
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
        return TokenResponse(**result)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


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
    return await service.get_user_orgs(auth.user_uuid)


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
        body: Request containing the user's email.
        service: Auth service.
        recovery_adapter: Password recovery adapter.
        frontend_url: Frontend URL for building reset links.

    Returns:
        Success message.
    """
    # Always succeeds (for security - doesn't reveal if email exists)
    await service.request_password_reset(
        email=body.email,
        recovery_adapter=recovery_adapter,
        frontend_url=frontend_url,
    )

    return {"message": "If an account with that email exists, we've sent a password reset link."}


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    body: PasswordResetConfirm,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    """Reset password using a valid token.

    Args:
        body: Request containing the reset token and new password.
        service: Auth service.

    Returns:
        Success message.

    Raises:
        HTTPException: If token is invalid, expired, or already used.
    """
    try:
        await service.reset_password(
            token=body.token,
            new_password=body.new_password,
        )
        return {"message": "Password has been reset successfully."}
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
