"""User management routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.auth.types import OrgRole as AuthOrgRole
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing.entrypoints.api.middleware.jwt_auth import (
    JwtContext,
    RequireAdmin,
    verify_jwt,
)

router = APIRouter(prefix="/users", tags=["users"])

# Annotated types for dependency injection
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]


UserRole = Literal["admin", "member", "viewer"]


class UserResponse(BaseModel):
    """Response for a user."""

    id: str
    email: str
    name: str | None = None
    role: UserRole
    is_active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    """Response for listing users."""

    users: list[UserResponse]
    total: int


class CreateUserRequest(BaseModel):
    """Request to create a user."""

    email: EmailStr
    name: str | None = Field(None, max_length=100)
    role: UserRole = "member"


class UpdateUserRequest(BaseModel):
    """Request to update a user."""

    name: str | None = Field(None, max_length=100)
    role: UserRole | None = None
    is_active: bool | None = None


@router.get("/", response_model=UserListResponse)
async def list_users(
    auth: AuthDep,
    app_db: AppDbDep,
) -> UserListResponse:
    """List all users for the tenant."""
    users = await app_db.fetch_all(
        """SELECT id, email, name, role, is_active, created_at
           FROM users
           WHERE tenant_id = $1
           ORDER BY created_at DESC""",
        auth.tenant_id,
    )

    return UserListResponse(
        users=[
            UserResponse(
                id=str(u["id"]),
                email=u["email"],
                name=u.get("name"),
                role=u["role"],
                is_active=u["is_active"],
                created_at=u["created_at"],
            )
            for u in users
        ],
        total=len(users),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    auth: AuthDep,
    app_db: AppDbDep,
) -> UserResponse:
    """Get the current authenticated user's profile."""
    if not auth.user_id:
        raise HTTPException(
            status_code=400,
            detail="No user associated with this API key",
        )

    user = await app_db.fetch_one(
        "SELECT * FROM users WHERE id = $1 AND tenant_id = $2",
        auth.user_id,
        auth.tenant_id,
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=str(user["id"]),
        email=user["email"],
        name=user.get("name"),
        role=user["role"],
        is_active=user["is_active"],
        created_at=user["created_at"],
    )


# ============================================================================
# JWT-based Organization Member Management (must be before /{user_id} routes)
# ============================================================================


class OrgMemberResponse(BaseModel):
    """Response for an org member."""

    user_id: str
    email: str
    name: str | None
    role: str
    created_at: datetime


class UpdateRoleRequest(BaseModel):
    """Request to update a member's role."""

    role: str


@router.get("/org-members", response_model=list[OrgMemberResponse])
async def list_org_members(
    auth: Annotated[JwtContext, Depends(verify_jwt)],
    app_db: AppDbDep,
) -> list[OrgMemberResponse]:
    """List all members of the current organization (JWT auth)."""
    org_id = auth.org_uuid

    # Get all org members with user info
    members = await app_db.fetch_all(
        """
        SELECT u.id as user_id, u.email, u.name, m.role, m.created_at
        FROM users u
        JOIN org_memberships m ON u.id = m.user_id
        WHERE m.org_id = $1
        ORDER BY m.created_at DESC
        """,
        org_id,
    )

    return [
        OrgMemberResponse(
            user_id=str(m["user_id"]),
            email=m["email"],
            name=m.get("name"),
            role=m["role"],
            created_at=m["created_at"],
        )
        for m in members
    ]


class InviteUserRequest(BaseModel):
    """Request to invite a user to the organization."""

    email: EmailStr
    role: str = "member"


@router.post("/invite", status_code=201)
async def invite_user(
    body: InviteUserRequest,
    auth: RequireAdmin,
    app_db: AppDbDep,
) -> dict[str, str]:
    """Invite a user to the organization (admin only).

    If user exists, adds them to the org. If not, creates a new user.
    """
    org_id = auth.org_uuid

    # Validate role
    try:
        role = AuthOrgRole(body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}") from exc

    if role == AuthOrgRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot assign owner role via invite")

    # Check if user already exists
    existing_user = await app_db.fetch_one(
        "SELECT id FROM users WHERE email = $1",
        body.email,
    )

    if existing_user:
        user_id = existing_user["id"]
        # Check if already a member
        existing_membership = await app_db.fetch_one(
            "SELECT user_id FROM org_memberships WHERE user_id = $1 AND org_id = $2",
            user_id,
            org_id,
        )
        if existing_membership:
            raise HTTPException(
                status_code=409,
                detail="User is already a member of this organization",
            )
    else:
        # Create new user
        result = await app_db.execute_returning(
            "INSERT INTO users (email) VALUES ($1) RETURNING id",
            body.email,
        )
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create user")
        user_id = result["id"]

    # Add to organization
    await app_db.execute(
        """
        INSERT INTO org_memberships (user_id, org_id, role)
        VALUES ($1, $2, $3)
        """,
        user_id,
        org_id,
        role.value,
    )

    return {"status": "invited", "user_id": str(user_id), "email": body.email}


# ============================================================================
# Legacy API Key-based User Management
# ============================================================================


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> UserResponse:
    """Get a specific user."""
    user = await app_db.fetch_one(
        "SELECT * FROM users WHERE id = $1 AND tenant_id = $2",
        user_id,
        auth.tenant_id,
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=str(user["id"]),
        email=user["email"],
        name=user.get("name"),
        role=user["role"],
        is_active=user["is_active"],
        created_at=user["created_at"],
    )


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(
    request: CreateUserRequest,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> UserResponse:
    """Create a new user.

    Requires admin scope.
    """
    # Check if email already exists for this tenant
    existing = await app_db.fetch_one(
        "SELECT id FROM users WHERE tenant_id = $1 AND email = $2",
        auth.tenant_id,
        request.email,
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="A user with this email already exists",
        )

    result = await app_db.execute_returning(
        """INSERT INTO users (tenant_id, email, name, role)
           VALUES ($1, $2, $3, $4)
           RETURNING *""",
        auth.tenant_id,
        request.email,
        request.name,
        request.role,
    )

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to create user")

    return UserResponse(
        id=str(result["id"]),
        email=result["email"],
        name=result.get("name"),
        role=result["role"],
        is_active=result["is_active"],
        created_at=result["created_at"],
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    request: UpdateUserRequest,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> UserResponse:
    """Update a user.

    Requires admin scope.
    """
    # Build update query dynamically
    updates: list[str] = []
    args: list[Any] = [user_id, auth.tenant_id]
    idx = 3

    if request.name is not None:
        updates.append(f"name = ${idx}")
        args.append(request.name)
        idx += 1

    if request.role is not None:
        updates.append(f"role = ${idx}")
        args.append(request.role)
        idx += 1

    if request.is_active is not None:
        updates.append(f"is_active = ${idx}")
        args.append(request.is_active)
        idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    query = f"""UPDATE users SET {", ".join(updates)}
                WHERE id = $1 AND tenant_id = $2
                RETURNING *"""

    result = await app_db.execute_returning(query, *args)

    if not result:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=str(result["id"]),
        email=result["email"],
        name=result.get("name"),
        role=result["role"],
        is_active=result["is_active"],
        created_at=result["created_at"],
    )


@router.delete("/{user_id}", status_code=204, response_class=Response)
async def deactivate_user(
    user_id: UUID,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> Response:
    """Deactivate a user (soft delete).

    Requires admin scope. Users cannot delete themselves.
    """
    # Prevent self-deletion
    if auth.user_id and str(auth.user_id) == str(user_id):
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate your own account",
        )

    result = await app_db.execute(
        "UPDATE users SET is_active = false WHERE id = $1 AND tenant_id = $2",
        user_id,
        auth.tenant_id,
    )

    if "UPDATE 0" in result:
        raise HTTPException(status_code=404, detail="User not found")

    return Response(status_code=204)


@router.patch("/{user_id}/role")
async def update_member_role(
    user_id: UUID,
    body: UpdateRoleRequest,
    auth: RequireAdmin,
    app_db: AppDbDep,
) -> dict[str, str]:
    """Update a member's role in the organization (admin only)."""
    org_id = auth.org_uuid
    current_user_id = auth.user_uuid

    # Cannot change own role
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    # Validate role
    try:
        new_role = AuthOrgRole(body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}") from exc

    # Cannot assign owner role
    if new_role == AuthOrgRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot assign owner role")

    # Update role
    result = await app_db.execute(
        """
        UPDATE org_memberships
        SET role = $3
        WHERE user_id = $1 AND org_id = $2
        """,
        user_id,
        org_id,
        new_role.value,
    )

    if "UPDATE 0" in result:
        raise HTTPException(status_code=404, detail="Member not found")

    return {"status": "updated", "role": new_role.value}


@router.post("/{user_id}/remove")
async def remove_org_member(
    user_id: UUID,
    auth: RequireAdmin,
    app_db: AppDbDep,
) -> dict[str, str]:
    """Remove a member from the organization (admin only)."""
    org_id = auth.org_uuid
    current_user_id = auth.user_uuid

    # Cannot remove self
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    # Check if target is owner
    membership = await app_db.fetch_one(
        "SELECT role FROM org_memberships WHERE user_id = $1 AND org_id = $2",
        user_id,
        org_id,
    )

    if not membership:
        raise HTTPException(status_code=404, detail="Member not found")

    if membership["role"] == AuthOrgRole.OWNER.value:
        raise HTTPException(status_code=400, detail="Cannot remove organization owner")

    # Remove from all teams in this org first
    await app_db.execute(
        """
        DELETE FROM team_memberships
        WHERE user_id = $1 AND team_id IN (
            SELECT id FROM teams WHERE org_id = $2
        )
        """,
        user_id,
        org_id,
    )

    # Remove from org
    await app_db.execute(
        "DELETE FROM org_memberships WHERE user_id = $1 AND org_id = $2",
        user_id,
        org_id,
    )

    return {"status": "removed"}
