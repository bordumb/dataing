"""Tags API routes."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.rbac import TagsRepository
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tags", tags=["tags"])

# Annotated types for dependency injection
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]


class TagCreate(BaseModel):
    """Tag creation request."""

    name: str
    color: str = "#6366f1"


class TagUpdate(BaseModel):
    """Tag update request."""

    name: str | None = None
    color: str | None = None


class TagResponse(BaseModel):
    """Tag response."""

    id: UUID
    name: str
    color: str

    class Config:
        """Pydantic config."""

        from_attributes = True


class TagListResponse(BaseModel):
    """Response for listing tags."""

    tags: list[TagResponse]
    total: int


class InvestigationTagAdd(BaseModel):
    """Add tag to investigation request."""

    tag_id: UUID


@router.get("/", response_model=TagListResponse)
async def list_tags(
    auth: AuthDep,
    app_db: AppDbDep,
) -> TagListResponse:
    """List all tags in the organization."""
    async with app_db.acquire() as conn:
        repo = TagsRepository(conn)
        tags = await repo.list_by_org(auth.tenant_id)

        result = [
            TagResponse(
                id=tag.id,
                name=tag.name,
                color=tag.color,
            )
            for tag in tags
        ]
        return TagListResponse(tags=result, total=len(result))


@router.post("/", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> TagResponse:
    """Create a new tag.

    Requires admin scope.
    """
    async with app_db.acquire() as conn:
        repo = TagsRepository(conn)

        # Check if tag with same name exists
        existing = await repo.get_by_name(auth.tenant_id, body.name)
        if existing:
            raise HTTPException(
                status_code=409,
                detail="A tag with this name already exists",
            )

        tag = await repo.create(org_id=auth.tenant_id, name=body.name, color=body.color)
        return TagResponse(
            id=tag.id,
            name=tag.name,
            color=tag.color,
        )


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(
    tag_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> TagResponse:
    """Get a tag by ID."""
    async with app_db.acquire() as conn:
        repo = TagsRepository(conn)
        tag = await repo.get_by_id(tag_id)

        if not tag or tag.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Tag not found")

        return TagResponse(
            id=tag.id,
            name=tag.name,
            color=tag.color,
        )


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: UUID,
    body: TagUpdate,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> TagResponse:
    """Update a tag.

    Requires admin scope.
    """
    async with app_db.acquire() as conn:
        repo = TagsRepository(conn)
        tag = await repo.get_by_id(tag_id)

        if not tag or tag.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Tag not found")

        # Check for name conflict if updating name
        if body.name and body.name != tag.name:
            existing = await repo.get_by_name(auth.tenant_id, body.name)
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail="A tag with this name already exists",
                )

        updated = await repo.update(tag_id, name=body.name, color=body.color)
        if not updated:
            raise HTTPException(status_code=404, detail="Tag not found")

        return TagResponse(
            id=updated.id,
            name=updated.name,
            color=updated.color,
        )


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_tag(
    tag_id: UUID,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> Response:
    """Delete a tag.

    Requires admin scope.
    """
    async with app_db.acquire() as conn:
        repo = TagsRepository(conn)
        tag = await repo.get_by_id(tag_id)

        if not tag or tag.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Tag not found")

        await repo.delete(tag_id)
        return Response(status_code=204)


# Investigation tag routes
investigation_tags_router = APIRouter(
    prefix="/investigations/{investigation_id}/tags",
    tags=["investigation-tags"],
)


@investigation_tags_router.get("/", response_model=list[TagResponse])
async def get_investigation_tags(
    investigation_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> list[TagResponse]:
    """Get all tags on an investigation."""
    # Verify investigation belongs to tenant
    investigation = await app_db.get_investigation(investigation_id, auth.tenant_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    async with app_db.acquire() as conn:
        repo = TagsRepository(conn)
        tags = await repo.get_investigation_tags(investigation_id)

        return [
            TagResponse(
                id=tag.id,
                name=tag.name,
                color=tag.color,
            )
            for tag in tags
        ]


@investigation_tags_router.post("/", status_code=status.HTTP_201_CREATED)
async def add_investigation_tag(
    investigation_id: UUID,
    body: InvestigationTagAdd,
    auth: AuthDep,
    app_db: AppDbDep,
) -> dict[str, str]:
    """Add a tag to an investigation."""
    # Verify investigation belongs to tenant
    investigation = await app_db.get_investigation(investigation_id, auth.tenant_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    async with app_db.acquire() as conn:
        repo = TagsRepository(conn)

        # Verify tag belongs to tenant
        tag = await repo.get_by_id(body.tag_id)
        if not tag or tag.org_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Tag not found")

        success = await repo.add_to_investigation(investigation_id, body.tag_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to add tag")

        return {"message": "Tag added"}


@investigation_tags_router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_investigation_tag(
    investigation_id: UUID,
    tag_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> Response:
    """Remove a tag from an investigation."""
    # Verify investigation belongs to tenant
    investigation = await app_db.get_investigation(investigation_id, auth.tenant_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    async with app_db.acquire() as conn:
        repo = TagsRepository(conn)
        await repo.remove_from_investigation(investigation_id, tag_id)
        return Response(status_code=204)
