"""SSO authentication endpoints."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from asyncpg import Connection
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from dataing.adapters.auth.postgres import PostgresAuthRepository
from dataing.adapters.db.app_db import AppDatabase
from dataing.core.auth.jwt import create_access_token, create_refresh_token
from dataing.core.auth.types import OrgRole
from dataing_ee.adapters.sso import (
    InvalidClaimsError,
    InvalidSignatureError,
    OIDCConfig,
    OIDCProvider,
    SSORepository,
    SSOStateRepository,
    StateConsumedError,
    StateExpiredError,
    StateNotFoundError,
    TokenExpiredError,
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
    request: Request,
    code: str,
    state: str,
    state_repo: StateRepoDep,
    sso_repo: SSORepoDep,
) -> SSOTokenResponse:
    """Handle SSO callback from IdP.

    Exchanges authorization code for tokens, creates/updates user,
    and issues JWT tokens.

    Args:
        request: FastAPI request for accessing app state.
        code: Authorization code from IdP.
        state: State parameter for CSRF protection.
        state_repo: SSO state repository for state validation.
        sso_repo: SSO repository for config and identity lookups.

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

    # Get SSO config for the organization
    sso_config = await sso_repo.get_sso_config(sso_state.org_id)
    if not sso_config or not sso_config.is_enabled:
        logger.error(f"SSO config not found or disabled for org: {sso_state.org_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO is not configured for this organization",
        )

    # Get decrypted client secret
    client_secret = await sso_repo.get_decrypted_client_secret(sso_state.org_id)
    if not client_secret or not sso_config.oidc_issuer_url or not sso_config.oidc_client_id:
        logger.error(f"Incomplete OIDC config for org: {sso_state.org_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SSO configuration is incomplete",
        )

    # Build OIDC provider
    oidc_config = OIDCConfig(
        issuer_url=sso_config.oidc_issuer_url,
        client_id=sso_config.oidc_client_id,
        client_secret=client_secret,
        redirect_uri=_get_redirect_uri(),
    )
    provider = OIDCProvider(oidc_config)

    # Exchange authorization code for tokens
    try:
        tokens = await provider.exchange_code(code)
        logger.debug(f"Token exchange successful for org: {sso_state.org_id}")
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code",
        ) from None

    # Verify ID token with nonce
    try:
        claims = await provider.verify_id_token(tokens.id_token, nonce=sso_state.nonce)
        logger.debug(f"ID token verified for sub: {claims.get('sub')}")
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID token has expired",
        ) from None
    except InvalidSignatureError as e:
        logger.error(f"ID token signature invalid: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID token signature verification failed",
        ) from None
    except InvalidClaimsError as e:
        logger.error(f"ID token claims invalid: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID token validation failed",
        ) from None

    # Extract user info from claims
    idp_user_id = claims["sub"]
    email = claims.get("email")
    email_verified = claims.get("email_verified", False)

    if not email:
        # Try to get email from userinfo endpoint
        try:
            user_info = await provider.get_user_info(tokens.access_token)
            email = user_info.email
            email_verified = user_info.email_verified
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not retrieve user email from identity provider",
            ) from None

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not provided by identity provider",
        )

    # Get auth repository for user operations
    app_db = get_app_db(request)
    auth_repo = PostgresAuthRepository(app_db)

    # Look up existing SSO identity
    sso_identity = await sso_repo.get_sso_identity(sso_config.id, idp_user_id)

    if sso_identity:
        # Existing SSO identity - get the linked user
        user = await auth_repo.get_user_by_id(sso_identity.user_id)
        if not user:
            logger.error(f"SSO identity exists but user not found: {sso_identity.user_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User account not found",
            )
        logger.info(f"SSO login for existing user: {user.id}")
    else:
        # No SSO identity - JIT provision user or link existing
        # First check if user exists by email
        existing_user = await auth_repo.get_user_by_email(email)

        if existing_user:
            # User exists but no SSO identity - link them if email is verified
            if not email_verified:
                # Security: Don't link accounts without verified email
                logger.warning(
                    f"SSO login blocked: unverified email {email} for existing user"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Cannot link SSO to existing account: email not verified by "
                        "identity provider. Please verify your email with your IdP."
                    ),
                )
            user = existing_user
            logger.info(
                "Linking existing user to SSO identity",
                extra={
                    "user_id": str(user.id),
                    "email": email,
                    "idp_user_id": idp_user_id,
                    "org_id": str(sso_state.org_id),
                },
            )
        else:
            # Create new user (JIT provisioning)
            name = claims.get("name") or claims.get("given_name")
            user = await auth_repo.create_user(
                email=email,
                name=name,
                password_hash=None,  # SSO users don't have passwords
            )
            # Add user to organization
            await auth_repo.add_user_to_org(
                user_id=user.id,
                org_id=sso_state.org_id,
                role=OrgRole.MEMBER,
            )
            logger.info(f"JIT provisioned new user: {user.id}")

        # Create SSO identity link
        await sso_repo.create_sso_identity(
            user_id=user.id,
            sso_config_id=sso_config.id,
            idp_user_id=idp_user_id,
        )

    # Get user's org membership for JWT claims
    membership = await auth_repo.get_user_org_membership(user.id, sso_state.org_id)
    if not membership:
        # User isn't a member of this org - add them
        membership = await auth_repo.add_user_to_org(
            user_id=user.id,
            org_id=sso_state.org_id,
            role=OrgRole.MEMBER,
        )

    # Get user's teams for JWT claims
    teams = await auth_repo.get_user_teams(user.id, sso_state.org_id)
    team_ids = [str(t.id) for t in teams]

    # Issue JWT tokens
    access_token = create_access_token(
        user_id=str(user.id),
        org_id=str(sso_state.org_id),
        role=membership.role.value,
        teams=team_ids,
    )
    refresh_token = create_refresh_token(user_id=str(user.id))

    logger.info(f"SSO authentication successful for user: {user.id}")
    return SSOTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )
