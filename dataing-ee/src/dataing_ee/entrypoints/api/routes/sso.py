"""SSO authentication endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from dataing_ee.adapters.sso import (
    SSOStateRepository,
    StateConsumedError,
    StateExpiredError,
    StateNotFoundError,
)
from dataing_ee.core.sso import SSOProviderType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/sso", tags=["sso"])


class SSODiscoverRequest(BaseModel):
    """Request to discover SSO method for an email."""

    email: EmailStr


class SSODiscoverResponse(BaseModel):
    """Response with SSO discovery result."""

    method: str  # "password", "oidc", or "saml"
    auth_url: str | None = None
    state: str | None = None
    display_name: str | None = None


class SSOCallbackRequest(BaseModel):
    """Request for SSO callback processing."""

    code: str
    state: str


class SSOTokenResponse(BaseModel):
    """Response with JWT tokens after SSO authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# Placeholder for dependency injection - will be implemented in fn-6.4/fn-6.5
async def get_sso_state_repository() -> SSOStateRepository:
    """Get SSO state repository.

    This is a placeholder that will be replaced with proper
    database connection injection in fn-6.4/fn-6.5.
    """
    # TODO: Wire database connection via dependency injection
    msg = "SSO state repository not yet configured"
    raise NotImplementedError(msg)


def _extract_domain(email: str) -> str:
    """Extract domain from email address."""
    return email.split("@")[1].lower()


@router.post("/discover", response_model=SSODiscoverResponse)
async def discover_sso_method(
    body: SSODiscoverRequest,
) -> SSODiscoverResponse:
    """Discover SSO method for an email address.

    Checks if the email domain is claimed by an organization with SSO configured.
    Returns the appropriate authentication method.

    Args:
        body: Request with email address.

    Returns:
        SSO discovery result with method and optional auth URL.
    """
    domain = _extract_domain(body.email)
    logger.info(f"SSO discovery for domain: {domain}")

    # TODO: Look up domain claim in database
    # For now, return password method (no SSO configured)
    # In production:
    # 1. Query domain_claims table for verified domain
    # 2. If found, get sso_config for the org
    # 3. Build auth URL based on provider type (OIDC or SAML)

    return SSODiscoverResponse(
        method="password",
        auth_url=None,
        state=None,
        display_name=None,
    )


@router.get("/callback")
async def sso_callback(
    code: str,
    state: str,
    state_repo: SSOStateRepository = Depends(get_sso_state_repository),
) -> SSOTokenResponse:
    """Handle SSO callback from IdP.

    Exchanges authorization code for tokens, creates/updates user,
    and issues JWT tokens.

    Args:
        code: Authorization code from IdP.
        state: State parameter for CSRF protection.
        state_repo: SSO state repository for state validation.

    Returns:
        JWT access and refresh tokens.

    Raises:
        HTTPException: If state is invalid, expired, or already used.
    """
    # Validate and consume state (single-use for CSRF protection)
    try:
        sso_state = await state_repo.validate_and_consume(state)
        logger.info(f"Processing SSO callback for org: {sso_state.org_id}")
    except StateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        ) from None
    except StateExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO session has expired. Please try again.",
        ) from None
    except StateConsumedError:
        logger.warning(f"SSO state replay attempt detected: {state[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This SSO session has already been used",
        ) from None

    # TODO: Implement token exchange (fn-6.5)
    # 1. Get SSO config from sso_state.org_id
    # 2. Exchange code for tokens with IdP
    # 3. Verify ID token with sso_state.nonce
    # 4. Extract user info from ID token
    # 5. JIT create or update user
    # 6. Issue JWT tokens

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SSO callback not yet implemented",
    )
