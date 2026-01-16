"""API routes for SLA policy management.

This module provides endpoints for creating, reading, updating, and listing
SLA policies for issue resolution time tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sla-policies", tags=["sla-policies"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


# ============================================================================
# Request/Response Schemas
# ============================================================================


class SeverityOverride(BaseModel):
    """Override SLA times for a specific severity."""

    time_to_acknowledge: int | None = Field(
        default=None, description="Minutes to acknowledge (OPEN -> TRIAGED)"
    )
    time_to_progress: int | None = Field(
        default=None, description="Minutes to progress (TRIAGED -> IN_PROGRESS)"
    )
    time_to_resolve: int | None = Field(
        default=None, description="Minutes to resolve (any -> RESOLVED)"
    )


class SLAPolicyCreate(BaseModel):
    """Request to create an SLA policy."""

    name: str = Field(..., min_length=1, max_length=100)
    is_default: bool = Field(default=False)
    time_to_acknowledge: int | None = Field(
        default=None, ge=1, description="Minutes to acknowledge"
    )
    time_to_progress: int | None = Field(default=None, ge=1, description="Minutes to progress")
    time_to_resolve: int | None = Field(default=None, ge=1, description="Minutes to resolve")
    severity_overrides: dict[str, SeverityOverride] | None = Field(
        default=None, description="Per-severity overrides (low, medium, high, critical)"
    )


class SLAPolicyUpdate(BaseModel):
    """Request to update an SLA policy."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_default: bool | None = None
    time_to_acknowledge: int | None = Field(default=None, ge=1)
    time_to_progress: int | None = Field(default=None, ge=1)
    time_to_resolve: int | None = Field(default=None, ge=1)
    severity_overrides: dict[str, SeverityOverride] | None = None


class SLAPolicyResponse(BaseModel):
    """SLA policy response."""

    id: UUID
    tenant_id: UUID
    name: str
    is_default: bool
    time_to_acknowledge: int | None
    time_to_progress: int | None
    time_to_resolve: int | None
    severity_overrides: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SLAPolicyListResponse(BaseModel):
    """Paginated SLA policy list response."""

    items: list[SLAPolicyResponse]
    total: int


# ============================================================================
# Helper Functions
# ============================================================================


async def _get_default_policy(db: AppDatabase, tenant_id: UUID) -> dict[str, Any] | None:
    """Get the default SLA policy for a tenant."""
    result: dict[str, Any] | None = await db.fetch_one(
        """
        SELECT id, tenant_id, name, is_default, time_to_acknowledge,
               time_to_progress, time_to_resolve, severity_overrides,
               created_at, updated_at
        FROM sla_policies
        WHERE tenant_id = $1 AND is_default = true
        """,
        tenant_id,
    )
    return result


async def _clear_default_policy(db: AppDatabase, tenant_id: UUID) -> None:
    """Clear any existing default policy for a tenant."""
    await db.execute(
        "UPDATE sla_policies SET is_default = false WHERE tenant_id = $1 AND is_default = true",
        tenant_id,
    )


def _row_to_response(row: dict[str, Any]) -> SLAPolicyResponse:
    """Convert database row to response model."""
    return SLAPolicyResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        is_default=row["is_default"],
        time_to_acknowledge=row["time_to_acknowledge"],
        time_to_progress=row["time_to_progress"],
        time_to_resolve=row["time_to_resolve"],
        severity_overrides=row["severity_overrides"] or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ============================================================================
# API Routes
# ============================================================================


@router.get("", response_model=SLAPolicyListResponse)
async def list_sla_policies(
    auth: AuthDep,
    db: AppDbDep,
    include_default: bool = Query(default=True, description="Include default policy"),
) -> SLAPolicyListResponse:
    """List SLA policies for the tenant."""
    rows = await db.fetch_all(
        """
        SELECT id, tenant_id, name, is_default, time_to_acknowledge,
               time_to_progress, time_to_resolve, severity_overrides,
               created_at, updated_at
        FROM sla_policies
        WHERE tenant_id = $1
        ORDER BY is_default DESC, name ASC
        """,
        auth.tenant_id,
    )
    items = [_row_to_response(row) for row in rows]
    return SLAPolicyListResponse(items=items, total=len(items))


@router.post("", response_model=SLAPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_sla_policy(
    auth: AdminScopeDep,
    db: AppDbDep,
    body: SLAPolicyCreate,
) -> SLAPolicyResponse:
    """Create a new SLA policy.

    Requires admin scope. If is_default is true, clears any existing default.
    """
    # If setting as default, clear existing default
    if body.is_default:
        await _clear_default_policy(db, auth.tenant_id)

    # Serialize severity overrides
    overrides_json = to_json_string(body.severity_overrides or {})

    row = await db.fetch_one(
        """
        INSERT INTO sla_policies (
            tenant_id, name, is_default, time_to_acknowledge,
            time_to_progress, time_to_resolve, severity_overrides
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, tenant_id, name, is_default, time_to_acknowledge,
                  time_to_progress, time_to_resolve, severity_overrides,
                  created_at, updated_at
        """,
        auth.tenant_id,
        body.name,
        body.is_default,
        body.time_to_acknowledge,
        body.time_to_progress,
        body.time_to_resolve,
        overrides_json,
    )

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create SLA policy")

    return _row_to_response(row)


@router.get("/default", response_model=SLAPolicyResponse | None)
async def get_default_sla_policy(
    auth: AuthDep,
    db: AppDbDep,
) -> SLAPolicyResponse | None:
    """Get the default SLA policy for the tenant.

    Returns None if no default policy is configured.
    """
    row = await _get_default_policy(db, auth.tenant_id)
    if not row:
        return None
    return _row_to_response(row)


@router.get("/{policy_id}", response_model=SLAPolicyResponse)
async def get_sla_policy(
    policy_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> SLAPolicyResponse:
    """Get an SLA policy by ID."""
    row = await db.fetch_one(
        """
        SELECT id, tenant_id, name, is_default, time_to_acknowledge,
               time_to_progress, time_to_resolve, severity_overrides,
               created_at, updated_at
        FROM sla_policies
        WHERE id = $1 AND tenant_id = $2
        """,
        policy_id,
        auth.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="SLA policy not found")
    return _row_to_response(row)


@router.patch("/{policy_id}", response_model=SLAPolicyResponse)
async def update_sla_policy(
    policy_id: UUID,
    auth: AdminScopeDep,
    db: AppDbDep,
    body: SLAPolicyUpdate,
) -> SLAPolicyResponse:
    """Update an SLA policy.

    Requires admin scope. If is_default is set to true, clears any existing default.
    """
    # Check policy exists and belongs to tenant
    existing = await db.fetch_one(
        "SELECT id FROM sla_policies WHERE id = $1 AND tenant_id = $2",
        policy_id,
        auth.tenant_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="SLA policy not found")

    # If setting as default, clear existing default
    if body.is_default is True:
        await _clear_default_policy(db, auth.tenant_id)

    # Build update query dynamically
    updates = []
    params: list[Any] = []
    param_idx = 1

    if body.name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(body.name)
        param_idx += 1

    if body.is_default is not None:
        updates.append(f"is_default = ${param_idx}")
        params.append(body.is_default)
        param_idx += 1

    if body.time_to_acknowledge is not None:
        updates.append(f"time_to_acknowledge = ${param_idx}")
        params.append(body.time_to_acknowledge)
        param_idx += 1

    if body.time_to_progress is not None:
        updates.append(f"time_to_progress = ${param_idx}")
        params.append(body.time_to_progress)
        param_idx += 1

    if body.time_to_resolve is not None:
        updates.append(f"time_to_resolve = ${param_idx}")
        params.append(body.time_to_resolve)
        param_idx += 1

    if body.severity_overrides is not None:
        updates.append(f"severity_overrides = ${param_idx}")
        params.append(to_json_string(body.severity_overrides))
        param_idx += 1

    # Always update updated_at
    updates.append("updated_at = NOW()")

    if not updates:
        # No updates provided, return existing
        return await get_sla_policy(policy_id, auth, db)

    # Execute update
    params.extend([policy_id, auth.tenant_id])
    query = f"""
        UPDATE sla_policies
        SET {", ".join(updates)}
        WHERE id = ${param_idx} AND tenant_id = ${param_idx + 1}
        RETURNING id, tenant_id, name, is_default, time_to_acknowledge,
                  time_to_progress, time_to_resolve, severity_overrides,
                  created_at, updated_at
    """

    row = await db.fetch_one(query, *params)
    if not row:
        raise HTTPException(status_code=404, detail="SLA policy not found")

    return _row_to_response(row)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_sla_policy(
    policy_id: UUID,
    auth: AdminScopeDep,
    db: AppDbDep,
) -> Response:
    """Delete an SLA policy.

    Requires admin scope. Issues using this policy will have sla_policy_id set to NULL.
    """
    # Check policy exists and belongs to tenant
    existing = await db.fetch_one(
        "SELECT id, is_default FROM sla_policies WHERE id = $1 AND tenant_id = $2",
        policy_id,
        auth.tenant_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="SLA policy not found")

    # Delete (foreign key ON DELETE SET NULL handles issues)
    await db.execute("DELETE FROM sla_policies WHERE id = $1", policy_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
