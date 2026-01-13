"""Settings routes for tenant configuration."""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import httpx
from asyncpg import Connection
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, HttpUrl

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing_ee.adapters.audit import audited
from dataing_ee.adapters.sso import SSORepository
from dataing_ee.core.sso import SSOProviderType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

# Annotated types for dependency injection
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]


# --- Lineage Provider Configuration ---


class LineageProviderConfig(BaseModel):
    """Configuration for a lineage provider."""

    provider: str = Field(
        ...,
        description="Provider type (dbt, openlineage, airflow, dagster, datahub, static_sql)",
    )
    priority: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Priority for composite adapters (higher = preferred)",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific configuration",
    )

    class Config:
        """Pydantic config."""

        extra = "forbid"


# --- Tenant Settings ---


class TenantSettings(BaseModel):
    """Tenant-level settings."""

    name: str
    slug: str
    require_approval_for_queries: bool = False
    max_queries_per_investigation: int = 50
    notification_email: str | None = None
    slack_channel: str | None = None
    lineage_providers: list[LineageProviderConfig] = Field(
        default_factory=list,
        description="Configured lineage providers for this tenant",
    )


class UpdateTenantSettingsRequest(BaseModel):
    """Request to update tenant settings."""

    name: str | None = Field(None, min_length=1, max_length=200)
    require_approval_for_queries: bool | None = None
    max_queries_per_investigation: int | None = Field(None, ge=1, le=200)
    notification_email: str | None = None
    slack_channel: str | None = None
    lineage_providers: list[LineageProviderConfig] | None = Field(
        None,
        description="Lineage providers configuration",
    )


@router.get("/tenant", response_model=TenantSettings)
async def get_tenant_settings(
    auth: AuthDep,
    app_db: AppDbDep,
) -> TenantSettings:
    """Get current tenant settings."""
    tenant = await app_db.get_tenant(auth.tenant_id)

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    settings = tenant.get("settings", {})
    if isinstance(settings, str):
        settings = json.loads(settings)

    # Parse lineage providers
    lineage_providers_raw = settings.get("lineage_providers", [])
    lineage_providers = [
        LineageProviderConfig(**lp) if isinstance(lp, dict) else lp for lp in lineage_providers_raw
    ]

    return TenantSettings(
        name=tenant["name"],
        slug=tenant["slug"],
        require_approval_for_queries=settings.get("require_approval_for_queries", False),
        max_queries_per_investigation=settings.get("max_queries_per_investigation", 50),
        notification_email=settings.get("notification_email"),
        slack_channel=settings.get("slack_channel"),
        lineage_providers=lineage_providers,
    )


@router.patch("/tenant", response_model=TenantSettings)
@audited(action="settings.update", resource_type="settings")
async def update_tenant_settings(
    request: UpdateTenantSettingsRequest,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> TenantSettings:
    """Update tenant settings."""
    tenant = await app_db.get_tenant(auth.tenant_id)

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    current_settings = tenant.get("settings", {})
    if isinstance(current_settings, str):
        current_settings = json.loads(current_settings)

    # Update only provided fields
    if request.name is not None:
        # Name update requires special handling
        await app_db.execute(
            "UPDATE tenants SET name = $1 WHERE id = $2",
            request.name,
            auth.tenant_id,
        )

    if request.require_approval_for_queries is not None:
        current_settings["require_approval_for_queries"] = request.require_approval_for_queries
    if request.max_queries_per_investigation is not None:
        current_settings["max_queries_per_investigation"] = request.max_queries_per_investigation
    if request.notification_email is not None:
        current_settings["notification_email"] = request.notification_email
    if request.slack_channel is not None:
        current_settings["slack_channel"] = request.slack_channel
    if request.lineage_providers is not None:
        # Serialize lineage providers to dicts for JSON storage
        current_settings["lineage_providers"] = [
            lp.model_dump() for lp in request.lineage_providers
        ]

    # Save updated settings
    await app_db.execute(
        "UPDATE tenants SET settings = $1 WHERE id = $2",
        json.dumps(current_settings),
        auth.tenant_id,
    )

    # Fetch and return updated tenant
    return await get_tenant_settings(auth, app_db)


# --- Webhook Settings ---


class WebhookResponse(BaseModel):
    """Response for a webhook."""

    id: str
    url: str
    events: list[str]
    is_active: bool
    last_triggered_at: str | None = None
    last_status: int | None = None
    created_at: str


class CreateWebhookRequest(BaseModel):
    """Request to create a webhook."""

    url: HttpUrl
    events: list[str] = Field(..., min_length=1)


class WebhookCreatedResponse(BaseModel):
    """Response after creating a webhook with secret."""

    id: str
    url: str
    events: list[str]
    secret: str  # Only returned once


@router.get("/webhooks", response_model=list[WebhookResponse])
async def list_webhooks(
    auth: AuthDep,
    app_db: AppDbDep,
) -> list[WebhookResponse]:
    """List all webhooks for the tenant."""
    webhooks = await app_db.list_webhooks(auth.tenant_id)

    return [
        WebhookResponse(
            id=str(w["id"]),
            url=w["url"],
            events=w["events"] if isinstance(w["events"], list) else json.loads(w["events"]),
            is_active=w["is_active"],
            last_triggered_at=w["last_triggered_at"].isoformat()
            if w.get("last_triggered_at")
            else None,
            last_status=w.get("last_status"),
            created_at=w["created_at"].isoformat(),
        )
        for w in webhooks
    ]


@router.post("/webhooks", response_model=WebhookCreatedResponse, status_code=201)
@audited(action="webhook.create", resource_type="webhook")
async def create_webhook(
    request: CreateWebhookRequest,
    auth: WriteScopeDep,
    app_db: AppDbDep,
) -> WebhookCreatedResponse:
    """Create a new webhook.

    The secret is returned only once and should be saved securely.
    """
    # Generate a secret for signature verification
    secret = f"whsec_{secrets.token_urlsafe(32)}"

    result = await app_db.create_webhook(
        tenant_id=auth.tenant_id,
        url=str(request.url),
        events=request.events,
        secret=secret,
    )

    return WebhookCreatedResponse(
        id=str(result["id"]),
        url=str(request.url),
        events=request.events,
        secret=secret,
    )


@router.delete("/webhooks/{webhook_id}", status_code=204, response_class=Response)
@audited(action="webhook.delete", resource_type="webhook")
async def delete_webhook(
    webhook_id: UUID,
    auth: WriteScopeDep,
    app_db: AppDbDep,
) -> Response:
    """Delete a webhook."""
    result = await app_db.execute(
        "DELETE FROM webhooks WHERE id = $1 AND tenant_id = $2",
        webhook_id,
        auth.tenant_id,
    )

    if "DELETE 0" in result:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return Response(status_code=204)


# --- API Key Settings ---


class ApiKeyResponse(BaseModel):
    """Response for an API key (without revealing the key)."""

    id: str
    key_prefix: str
    name: str
    scopes: list[str]
    is_active: bool
    last_used_at: str | None = None
    expires_at: str | None = None
    created_at: str


class CreateApiKeyRequest(BaseModel):
    """Request to create an API key."""

    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default=["read", "write"])
    expires_in_days: int | None = Field(None, ge=1, le=365)


class ApiKeyCreatedResponse(BaseModel):
    """Response after creating an API key with the key value."""

    id: str
    key: str  # Full key, only returned once
    key_prefix: str
    name: str
    scopes: list[str]
    expires_at: str | None = None


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    auth: AuthDep,
    app_db: AppDbDep,
) -> list[ApiKeyResponse]:
    """List all API keys for the tenant."""
    keys = await app_db.list_api_keys(auth.tenant_id)

    return [
        ApiKeyResponse(
            id=str(k["id"]),
            key_prefix=k["key_prefix"],
            name=k["name"],
            scopes=k["scopes"] if isinstance(k["scopes"], list) else json.loads(k["scopes"]),
            is_active=k["is_active"],
            last_used_at=k["last_used_at"].isoformat() if k.get("last_used_at") else None,
            expires_at=k["expires_at"].isoformat() if k.get("expires_at") else None,
            created_at=k["created_at"].isoformat(),
        )
        for k in keys
    ]


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=201)
@audited(action="api_key.create", resource_type="api_key")
async def create_api_key(
    request: CreateApiKeyRequest,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> ApiKeyCreatedResponse:
    """Create a new API key.

    The full key is returned only once and should be saved securely.
    """
    from dataing.services.auth import AuthService

    auth_service = AuthService(app_db)
    result = await auth_service.create_api_key(
        tenant_id=auth.tenant_id,
        name=request.name,
        scopes=request.scopes,
        expires_in_days=request.expires_in_days,
    )

    return ApiKeyCreatedResponse(
        id=str(result.id),
        key=result.key,
        key_prefix=result.key_prefix,
        name=result.name,
        scopes=result.scopes,
        expires_at=result.expires_at.isoformat() if result.expires_at else None,
    )


@router.delete("/api-keys/{key_id}", status_code=204, response_class=Response)
@audited(action="api_key.revoke", resource_type="api_key")
async def revoke_api_key(
    key_id: UUID,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> Response:
    """Revoke an API key."""
    from dataing.services.auth import AuthService

    auth_service = AuthService(app_db)
    success = await auth_service.revoke_api_key(key_id, auth.tenant_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    return Response(status_code=204)


# --- SSO Configuration Settings ---


def get_app_db_from_request(request: Request) -> AppDatabase:
    """Get AppDatabase from app state."""
    return request.app.state.app_db


@asynccontextmanager
async def get_db_connection(app_db: AppDatabase) -> AsyncIterator[Connection]:
    """Get database connection from pool."""
    async with app_db.acquire() as conn:
        yield conn


async def get_sso_repository(request: Request) -> AsyncIterator[SSORepository]:
    """Get SSO repository with database connection."""
    app_db = get_app_db_from_request(request)
    async with get_db_connection(app_db) as conn:
        yield SSORepository(conn)


SSORepoDep = Annotated[SSORepository, Depends(get_sso_repository)]


class SSOConfigRequest(BaseModel):
    """Request to create or update SSO configuration."""

    provider_type: Literal["oidc"] = "oidc"
    display_name: str | None = Field(
        None, description="Display name for the SSO button (e.g., 'Sign in with Okta')"
    )
    oidc_issuer_url: str = Field(..., description="OIDC issuer URL (e.g., https://your-org.okta.com)")
    oidc_client_id: str = Field(..., description="OIDC client ID")
    oidc_client_secret: str = Field(..., description="OIDC client secret")


class SSOConfigResponse(BaseModel):
    """Response for SSO configuration (without secret)."""

    id: str
    provider_type: str
    display_name: str | None
    oidc_issuer_url: str
    oidc_client_id: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class SSOTestRequest(BaseModel):
    """Request to test SSO configuration."""

    oidc_issuer_url: str = Field(..., description="OIDC issuer URL to test")


class SSOTestResponse(BaseModel):
    """Response for SSO test."""

    success: bool
    message: str
    discovery_url: str | None = None


@router.get("/sso/config", response_model=SSOConfigResponse | None)
async def get_sso_config(
    auth: AdminScopeDep,
    sso_repo: SSORepoDep,
) -> SSOConfigResponse | None:
    """Get current SSO configuration for the organization.

    Returns None if SSO is not configured.
    """
    config = await sso_repo.get_sso_config(auth.tenant_id)

    if not config:
        return None

    return SSOConfigResponse(
        id=str(config.id),
        provider_type=config.provider_type.value,
        display_name=config.display_name,
        oidc_issuer_url=config.oidc_issuer_url or "",
        oidc_client_id=config.oidc_client_id or "",
        is_enabled=config.is_enabled,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.post("/sso/config", response_model=SSOConfigResponse, status_code=201)
@audited(action="sso.config.create", resource_type="sso_config")
async def create_or_update_sso_config(
    request: SSOConfigRequest,
    auth: AdminScopeDep,
    sso_repo: SSORepoDep,
) -> SSOConfigResponse:
    """Create or update SSO configuration for the organization.

    If SSO is already configured, this updates the existing configuration.
    The client secret is encrypted before storage.
    """
    # Check if config already exists
    existing = await sso_repo.get_sso_config(auth.tenant_id)

    if existing:
        # Update existing config
        # First update the main config
        updated = await sso_repo.update_sso_config(
            config_id=existing.id,
            is_enabled=True,
            display_name=request.display_name,
        )

        # Update client secret separately (it's encrypted)
        await sso_repo.update_client_secret(auth.tenant_id, request.oidc_client_secret)

        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update SSO configuration")

        return SSOConfigResponse(
            id=str(updated.id),
            provider_type=updated.provider_type.value,
            display_name=updated.display_name,
            oidc_issuer_url=updated.oidc_issuer_url or "",
            oidc_client_id=updated.oidc_client_id or "",
            is_enabled=updated.is_enabled,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )

    # Create new config
    config = await sso_repo.create_sso_config(
        org_id=auth.tenant_id,
        provider_type=SSOProviderType.OIDC,
        display_name=request.display_name,
        oidc_issuer_url=request.oidc_issuer_url,
        oidc_client_id=request.oidc_client_id,
        oidc_client_secret=request.oidc_client_secret,
    )

    logger.info(f"SSO config created for org: {auth.tenant_id}")

    return SSOConfigResponse(
        id=str(config.id),
        provider_type=config.provider_type.value,
        display_name=config.display_name,
        oidc_issuer_url=config.oidc_issuer_url or "",
        oidc_client_id=config.oidc_client_id or "",
        is_enabled=config.is_enabled,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.delete("/sso/config", status_code=204, response_class=Response)
@audited(action="sso.config.disable", resource_type="sso_config")
async def disable_sso_config(
    auth: AdminScopeDep,
    sso_repo: SSORepoDep,
) -> Response:
    """Disable SSO configuration for the organization.

    This doesn't delete the configuration, just disables it.
    Existing SSO identities are preserved for re-enabling.
    """
    config = await sso_repo.get_sso_config(auth.tenant_id)

    if not config:
        raise HTTPException(status_code=404, detail="SSO configuration not found")

    await sso_repo.update_sso_config(config.id, is_enabled=False)

    logger.info(f"SSO config disabled for org: {auth.tenant_id}")

    return Response(status_code=204)


@router.post("/sso/test", response_model=SSOTestResponse)
async def test_sso_config(
    request: SSOTestRequest,
    auth: AdminScopeDep,
) -> SSOTestResponse:
    """Test SSO configuration by validating the OIDC discovery document.

    This endpoint checks if the IdP is reachable and returns valid OIDC metadata.
    """
    discovery_url = f"{request.oidc_issuer_url.rstrip('/')}/.well-known/openid-configuration"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(discovery_url)
            response.raise_for_status()
            data = response.json()

        # Validate required OIDC endpoints
        required_fields = ["authorization_endpoint", "token_endpoint", "jwks_uri"]
        missing = [f for f in required_fields if f not in data]

        if missing:
            return SSOTestResponse(
                success=False,
                message=f"OIDC discovery missing required fields: {', '.join(missing)}",
                discovery_url=discovery_url,
            )

        return SSOTestResponse(
            success=True,
            message="OIDC discovery document is valid and IdP is reachable",
            discovery_url=discovery_url,
        )

    except httpx.ConnectError:
        return SSOTestResponse(
            success=False,
            message=f"Could not connect to IdP at {request.oidc_issuer_url}",
            discovery_url=discovery_url,
        )
    except httpx.HTTPStatusError as e:
        return SSOTestResponse(
            success=False,
            message=f"IdP returned error: HTTP {e.response.status_code}",
            discovery_url=discovery_url,
        )
    except Exception as e:
        return SSOTestResponse(
            success=False,
            message=f"Failed to fetch OIDC discovery: {e}",
            discovery_url=discovery_url,
        )
