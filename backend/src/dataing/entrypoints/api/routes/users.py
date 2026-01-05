"""User management routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key

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
