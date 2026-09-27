"""User datasource credentials management routes.

This module provides API endpoints for users to manage their own
database credentials for each datasource.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from dataing.adapters.audit import audited
from dataing.adapters.datasource import SourceType, get_registry
from dataing.adapters.datasource.encryption import decrypt_config, get_encryption_key
from dataing.adapters.db.app_db import AppDatabase
from dataing.core.credentials import CredentialsService
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    require_scope,
    verify_api_key,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/datasources/{datasource_id}/credentials", tags=["credentials"])

# Annotated types for dependency injection
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]


# Request/Response Models


class SaveCredentialsRequest(BaseModel):
    """Request to save user credentials for a datasource."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)
    role: str | None = Field(None, max_length=255, description="Role for Snowflake")
    warehouse: str | None = Field(None, max_length=255, description="Warehouse for Snowflake")


class CredentialsStatusResponse(BaseModel):
    """Response for credentials status check."""

    configured: bool
    db_username: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None


class CredentialsTestResponse(BaseModel):
    """Response for testing credentials."""

    success: bool
    error: str | None = None
    tables_accessible: int | None = None


class DeleteCredentialsResponse(BaseModel):
    """Response for deleting credentials."""

    deleted: bool


# Route handlers


@router.post("", status_code=201)
@audited(action="credentials.save", resource_type="credentials", resource_id_param="datasource_id")
async def save_credentials(
    http_request: Request,
    datasource_id: UUID,
    body: SaveCredentialsRequest,
    auth: WriteScopeDep,
    app_db: AppDbDep,
) -> CredentialsStatusResponse:
    """Save or update credentials for a datasource.

    Users can store their own database credentials which will be used
    for query execution. The database enforces permissions, not Dataing.
    """
    # Verify datasource exists and belongs to tenant
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    # Verify user_id is available
    if not auth.user_id:
        raise HTTPException(status_code=400, detail="User ID required for credential storage")

    # Save credentials
    credentials_service = CredentialsService(app_db)
    await credentials_service.save_credentials(
        user_id=auth.user_id,
        datasource_id=datasource_id,
        credentials={
            "username": body.username,
            "password": body.password,
            "role": body.role,
            "warehouse": body.warehouse,
        },
    )

    # Return status
    status = await credentials_service.get_status(auth.user_id, datasource_id)
    return CredentialsStatusResponse(**status)


@router.get("", response_model=CredentialsStatusResponse)
async def get_credentials_status(
    datasource_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> CredentialsStatusResponse:
    """Check if credentials are configured for a datasource.

    Returns configuration status without exposing the actual credentials.
    """
    # Verify datasource exists and belongs to tenant
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    if not auth.user_id:
        return CredentialsStatusResponse(configured=False)

    credentials_service = CredentialsService(app_db)
    status = await credentials_service.get_status(auth.user_id, datasource_id)
    return CredentialsStatusResponse(**status)


@router.delete("", response_model=DeleteCredentialsResponse)
@audited(
    action="credentials.delete",
    resource_type="credentials",
    resource_id_param="datasource_id",
)
async def delete_credentials(
    http_request: Request,
    datasource_id: UUID,
    auth: WriteScopeDep,
    app_db: AppDbDep,
) -> DeleteCredentialsResponse:
    """Remove credentials for a datasource.

    After deletion, the user will need to reconfigure credentials
    before executing queries.
    """
    # Verify datasource exists and belongs to tenant
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    if not auth.user_id:
        raise HTTPException(status_code=400, detail="User ID required")

    credentials_service = CredentialsService(app_db)
    deleted = await credentials_service.delete_credentials(auth.user_id, datasource_id)
    return DeleteCredentialsResponse(deleted=deleted)


@router.post("/test", response_model=CredentialsTestResponse)
@audited(action="credentials.test", resource_type="credentials", resource_id_param="datasource_id")
async def test_credentials(
    http_request: Request,
    datasource_id: UUID,
    body: SaveCredentialsRequest,
    auth: WriteScopeDep,
    app_db: AppDbDep,
) -> CredentialsTestResponse:
    """Test credentials without saving them.

    Validates that the provided credentials can connect to the
    database and access tables.
    """
    # Verify datasource exists and belongs to tenant
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    registry = get_registry()

    try:
        source_type = SourceType(ds["type"])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {ds['type']}",
        ) from None

    if not registry.is_registered(source_type):
        raise HTTPException(
            status_code=400,
            detail=f"Source type not available: {ds['type']}",
        )

    # Decrypt base config and merge with test credentials
    encryption_key = get_encryption_key()
    try:
        base_config = decrypt_config(ds["connection_config_encrypted"], encryption_key)
    except Exception as e:
        return CredentialsTestResponse(
            success=False,
            error=f"Failed to decrypt datasource configuration: {e!s}",
        )

    # Build connection config with user credentials
    connection_config = {
        **base_config,
        "user": body.username,
        "password": body.password,
    }
    if body.role:
        connection_config["role"] = body.role
    if body.warehouse:
        connection_config["warehouse"] = body.warehouse

    # Test connection
    try:
        adapter = registry.create(source_type, connection_config)
        async with adapter:
            result = await adapter.test_connection()
            if not result.success:
                return CredentialsTestResponse(
                    success=False,
                    error=result.message,
                )

            # Try to count accessible tables
            tables_accessible = None
            if hasattr(adapter, "get_schema"):
                try:
                    from dataing.adapters.datasource import SchemaFilter

                    schema = await adapter.get_schema(SchemaFilter(max_tables=100))
                    tables_accessible = schema.table_count()
                except Exception:
                    pass  # Not critical if we can't count tables

            return CredentialsTestResponse(
                success=True,
                tables_accessible=tables_accessible,
            )
    except Exception as e:
        return CredentialsTestResponse(
            success=False,
            error=str(e),
        )
