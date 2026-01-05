"""Auth API routes for login, registration, and token refresh."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from dataing.adapters.auth.postgres import PostgresAuthRepository
from dataing.core.auth.service import AuthError, AuthService

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
async def get_current_user(request: Request) -> dict[str, Any]:
    """Get current authenticated user info.

    Requires JWT authentication via the jwt_auth middleware.
    """
    # This will be populated by JWT middleware
    if not hasattr(request.state, "user"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        "user_id": request.state.user.sub,
        "org_id": request.state.user.org_id,
        "role": request.state.user.role,
        "teams": request.state.user.teams,
    }


@router.get("/me/orgs")
async def get_user_orgs(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> list[dict[str, Any]]:
    """Get all organizations the current user belongs to.

    Returns list of orgs with role for each.
    """
    if not hasattr(request.state, "user"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = UUID(request.state.user.sub)
    return await service.get_user_orgs(user_id)
