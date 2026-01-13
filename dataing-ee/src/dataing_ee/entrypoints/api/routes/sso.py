"""SSO authentication endpoints."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from asyncpg import Connection
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from dataing.adapters.db.app_db import AppDatabase
from dataing_ee.adapters.sso import (
    OIDCConfig,
    OIDCProvider,
    SSORepository,
    SSOStateRepository,
    StateConsumedError,
    StateExpiredError,
    StateNotFoundError,
)
from dataing_ee.core.sso import SSOProviderType, decrypt_secret

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


def get_app_db(request: Request) -> AppDatabase:
    """Get AppDatabase from app state."""
    return request.app.state.app_db


@asynccontextmanager
async def get_db_connection(app_db: AppDatabase) -> AsyncIterator[Connection]:
    """Get database connection from pool."""
    async with app_db.acquire() as conn:
        yield conn


async def get_sso_state_repository(
    request: Request,
) -> AsyncIterator[SSOStateRepository]:
    """Get SSO state repository with database connection."""
    app_db = get_app_db(request)
    async with get_db_connection(app_db) as conn:
        yield SSOStateRepository(conn)


async def get_sso_repository(
    request: Request,
) -> AsyncIterator[SSORepository]:
    """Get SSO repository with database connection."""
    app_db = get_app_db(request)
    async with get_db_connection(app_db) as conn:
        yield SSORepository(conn)


# Annotated types for dependency injection
SSORepoDep = Annotated[SSORepository, Depends(get_sso_repository)]
StateRepoDep = Annotated[SSOStateRepository, Depends(get_sso_state_repository)]


def _extract_domain(email: str) -> str:
    """Extract domain from email address."""
    return email.split("@")[1].lower()


def _get_redirect_uri() -> str:
    """Get SSO callback redirect URI from environment."""
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return f"{frontend_url}/auth/sso/callback"


@router.post("/discover", response_model=SSODiscoverResponse)
async def discover_sso_method(
    body: SSODiscoverRequest,
    sso_repo: SSORepoDep,
    state_repo: StateRepoDep,
) -> SSODiscoverResponse:
    """Discover SSO method for an email address.

    Checks if the email domain is claimed by an organization with SSO configured.
    Returns the appropriate authentication method.

    Args:
        body: Request with email address.
        sso_repo: SSO repository for domain/config lookups.
        state_repo: SSO state repository for state creation.

    Returns:
        SSO discovery result with method and optional auth URL.
    """
    domain = _extract_domain(body.email)
    logger.info(f"SSO discovery for domain: {domain}")

    # Look up verified domain claim
    domain_claim = await sso_repo.get_domain_claim(domain)
    if not domain_claim or not domain_claim.is_verified:
        logger.debug(f"No verified domain claim for: {domain}")
        return SSODiscoverResponse(
            method="password",
            auth_url=None,
            state=None,
            display_name=None,
        )

    # Get SSO config for the organization
    sso_config = await sso_repo.get_sso_config(domain_claim.org_id)
    if not sso_config or not sso_config.is_enabled:
        logger.debug(f"No enabled SSO config for org: {domain_claim.org_id}")
        return SSODiscoverResponse(
            method="password",
            auth_url=None,
            state=None,
            display_name=None,
        )

    # Only OIDC is supported for now
    if sso_config.provider_type != SSOProviderType.OIDC:
        logger.warning(f"Unsupported SSO provider type: {sso_config.provider_type}")
        return SSODiscoverResponse(
            method="password",
            auth_url=None,
            state=None,
            display_name=None,
        )

    # Get decrypted client secret
    client_secret = await sso_repo.get_decrypted_client_secret(domain_claim.org_id)
    if not client_secret or not sso_config.oidc_issuer_url or not sso_config.oidc_client_id:
        logger.error(f"Incomplete OIDC config for org: {domain_claim.org_id}")
        return SSODiscoverResponse(
            method="password",
            auth_url=None,
            state=None,
            display_name=None,
        )

    # Create state and nonce for CSRF/replay protection
    sso_state = await state_repo.create_state(
        org_id=domain_claim.org_id,
        redirect_uri=_get_redirect_uri(),
    )

    # Build OIDC auth URL
    oidc_config = OIDCConfig(
        issuer_url=sso_config.oidc_issuer_url,
        client_id=sso_config.oidc_client_id,
        client_secret=client_secret,
        redirect_uri=_get_redirect_uri(),
    )
    provider = OIDCProvider(oidc_config)

    try:
        auth_url = await provider.get_authorization_url(
            state=sso_state.state_id,
            nonce=sso_state.nonce,
        )
    except Exception as e:
        logger.error(f"Failed to generate OIDC auth URL: {e}")
        return SSODiscoverResponse(
            method="password",
            auth_url=None,
            state=None,
            display_name=None,
        )

    logger.info(f"SSO discovery successful for domain: {domain}")
    return SSODiscoverResponse(
        method="oidc",
        auth_url=auth_url,
        state=sso_state.state_id,
        display_name=sso_config.display_name,
    )


@router.get("/callback")
async def sso_callback(
    code: str,
    state: str,
    state_repo: StateRepoDep,
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
