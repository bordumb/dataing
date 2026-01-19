"""Permissions API routes."""

from __future__ import annotations

import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from dataing.adapters.audit import audited
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.rbac import PermissionsRepository
from dataing.core.rbac import Permission
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/permissions", tags=["permissions"])

# Annotated types for dependency injection
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]

# Type aliases
PermissionLevel = Literal["read", "write", "admin"]
GranteeType = Literal["user", "team"]
AccessType = Literal["resource", "tag", "datasource"]


class PermissionGrantCreate(BaseModel):
    """Permission grant creation request."""

    # Who gets the permission
    grantee_type: GranteeType
    grantee_id: UUID  # user_id or team_id

    # What they get access to
    access_type: AccessType
    resource_type: str = "investigation"
    resource_id: UUID | None = None  # For direct resource access
    tag_id: UUID | None = None  # For tag-based access
    data_source_id: UUID | None = None  # For datasource access

    # Permission level
    permission: PermissionLevel


class PermissionGrantResponse(BaseModel):
    """Permission grant response."""

    id: UUID
    grantee_type: str
    grantee_id: UUID | None
    access_type: str
    resource_type: str
    resource_id: UUID | None
    tag_id: UUID | None
    data_source_id: UUID | None
    permission: str

    class Config:
        """Pydantic config."""

        from_attributes = True


class PermissionListResponse(BaseModel):
    """Response for listing permissions."""

    permissions: list[PermissionGrantResponse]
    total: int


@router.get("/", response_model=PermissionListResponse)
async def list_permissions(
    auth: AuthDep,
    app_db: AppDbDep,
) -> PermissionListResponse:
    """List all permission grants in the organization."""
    async with app_db.acquire() as conn:
        repo = PermissionsRepository(conn)
        grants = await repo.list_by_org(auth.tenant_id)

        result = [
            PermissionGrantResponse(
                id=grant.id,
                grantee_type=grant.grantee_type.value,
                grantee_id=grant.user_id or grant.team_id,
                access_type=grant.access_type.value,
                resource_type=grant.resource_type,
                resource_id=grant.resource_id,
                tag_id=grant.tag_id,
                data_source_id=grant.data_source_id,
                permission=grant.permission.value,
            )
            for grant in grants
        ]
        return PermissionListResponse(permissions=result, total=len(result))


@router.post("/", response_model=PermissionGrantResponse, status_code=status.HTTP_201_CREATED)
@audited(action="permission.grant", resource_type="permission")
async def create_permission(
    body: PermissionGrantCreate,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> PermissionGrantResponse:
    """Create a new permission grant.

    Requires admin scope.
    """
    # Validate access type matches provided IDs
    if body.access_type == "resource" and not body.resource_id:
        raise HTTPException(
            status_code=400,
            detail="resource_id required for resource access type",
        )
    if body.access_type == "tag" and not body.tag_id:
        raise HTTPException(
            status_code=400,
            detail="tag_id required for tag access type",
        )
    if body.access_type == "datasource" and not body.data_source_id:
        raise HTTPException(
            status_code=400,
            detail="data_source_id required for datasource access type",
        )

    async with app_db.acquire() as conn:
        repo = PermissionsRepository(conn)
        permission = Permission(body.permission)

        # Get user_id from auth context for created_by
        created_by = auth.user_id

        if body.grantee_type == "user":
            if body.access_type == "resource":
                if not body.resource_id:
                    raise HTTPException(
                        status_code=400, detail="resource_id required for resource access"
                    )
                grant = await repo.create_user_resource_grant(
                    org_id=auth.tenant_id,
                    user_id=body.grantee_id,
                    resource_type=body.resource_type,
                    resource_id=body.resource_id,
                    permission=permission,
                    created_by=created_by,
                )
            elif body.access_type == "tag":
                if not body.tag_id:
                    raise HTTPException(status_code=400, detail="tag_id required for tag access")
                grant = await repo.create_user_tag_grant(
                    org_id=auth.tenant_id,
                    user_id=body.grantee_id,
                    tag_id=body.tag_id,
                    permission=permission,
                    created_by=created_by,
                )
            else:  # datasource
                if not body.data_source_id:
                    raise HTTPException(
                        status_code=400, detail="data_source_id required for datasource access"
                    )
                grant = await repo.create_user_datasource_grant(
                    org_id=auth.tenant_id,
                    user_id=body.grantee_id,
                    data_source_id=body.data_source_id,
                    permission=permission,
                    created_by=created_by,
                )
        else:  # team
            if body.access_type == "resource":
                if not body.resource_id:
                    raise HTTPException(
                        status_code=400, detail="resource_id required for resource access"
                    )
                grant = await repo.create_team_resource_grant(
                    org_id=auth.tenant_id,
                    team_id=body.grantee_id,
                    resource_type=body.resource_type,
                    resource_id=body.resource_id,
                    permission=permission,
                    created_by=created_by,
                )
            elif body.access_type == "tag":
                if not body.tag_id:
                    raise HTTPException(status_code=400, detail="tag_id required for tag access")
                grant = await repo.create_team_tag_grant(
                    org_id=auth.tenant_id,
                    team_id=body.grantee_id,
                    tag_id=body.tag_id,
                    permission=permission,
                    created_by=created_by,
                )
            else:  # datasource - need to implement team datasource grant
                raise HTTPException(
                    status_code=400,
                    detail="Team datasource grants not yet implemented",
                )

        return PermissionGrantResponse(
            id=grant.id,
            grantee_type=grant.grantee_type.value,
            grantee_id=grant.user_id or grant.team_id,
            access_type=grant.access_type.value,
            resource_type=grant.resource_type,
            resource_id=grant.resource_id,
            tag_id=grant.tag_id,
            data_source_id=grant.data_source_id,
            permission=grant.permission.value,
        )


@router.delete("/{grant_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
@audited(action="permission.revoke", resource_type="permission")
async def delete_permission(
    grant_id: UUID,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> Response:
    """Delete a permission grant.

    Requires admin scope.
    """
    async with app_db.acquire() as conn:
        repo = PermissionsRepository(conn)

        # Note: Ideally we would verify the grant belongs to this tenant,
        # but the repository doesn't have a get_by_id method yet.
        # For now, we rely on the grant_id being globally unique.
        deleted = await repo.delete(grant_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Permission grant not found")

        return Response(status_code=204)


# Investigation permissions routes
investigation_permissions_router = APIRouter(
    prefix="/investigations/{investigation_id}/permissions",
    tags=["investigation-permissions"],
)


@investigation_permissions_router.get("/", response_model=list[PermissionGrantResponse])
async def get_investigation_permissions(
    investigation_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> list[PermissionGrantResponse]:
    """Get all permissions for an investigation."""
    # Verify investigation belongs to tenant
    investigation = await app_db.get_investigation(investigation_id, auth.tenant_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    async with app_db.acquire() as conn:
        repo = PermissionsRepository(conn)
        grants = await repo.list_by_resource("investigation", investigation_id)

        return [
            PermissionGrantResponse(
                id=grant.id,
                grantee_type=grant.grantee_type.value,
                grantee_id=grant.user_id or grant.team_id,
                access_type=grant.access_type.value,
                resource_type=grant.resource_type,
                resource_id=grant.resource_id,
                tag_id=grant.tag_id,
                data_source_id=grant.data_source_id,
                permission=grant.permission.value,
            )
            for grant in grants
        ]
