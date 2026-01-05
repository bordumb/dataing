"""SSO authentication endpoints."""

import logging
import secrets

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from dataing.core.sso import SSOProviderType

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


# In-memory state store (replace with Redis in production)
_sso_states: dict[str, dict[str, str]] = {}


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
) -> SSOTokenResponse:
    """Handle SSO callback from IdP.

    Exchanges authorization code for tokens, creates/updates user,
    and issues JWT tokens.

    Args:
        code: Authorization code from IdP.
        state: State parameter for CSRF protection.

    Returns:
        JWT access and refresh tokens.
    """
    # Validate state
    if state not in _sso_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )

    state_data = _sso_states.pop(state)
    logger.info(f"Processing SSO callback for org: {state_data.get('org_id')}")

    # TODO: Implement token exchange
    # 1. Get SSO config from state_data
    # 2. Exchange code for tokens with IdP
    # 3. Extract user info from ID token
    # 4. JIT create or update user
    # 5. Issue JWT tokens

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SSO callback not yet implemented",
    )


def generate_state(org_id: str, provider_type: SSOProviderType) -> str:
    """Generate and store state for SSO flow.

    Args:
        org_id: Organization ID.
        provider_type: SSO provider type.

    Returns:
        Random state string.
    """
    state = secrets.token_urlsafe(32)
    _sso_states[state] = {
        "org_id": org_id,
        "provider_type": provider_type.value,
    }
    return state
