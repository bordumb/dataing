"""API routes for schema comments."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/datasets/{dataset_id}/schema-comments", tags=["schema-comments"])

AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
DbDep = Annotated[AppDatabase, Depends(get_app_db)]


class SchemaCommentCreate(BaseModel):
    """Request body for creating a schema comment."""

    field_name: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    parent_id: UUID | None = None


class SchemaCommentUpdate(BaseModel):
    """Request body for updating a schema comment."""

    content: str = Field(..., min_length=1)


class SchemaCommentResponse(BaseModel):
    """Response for a schema comment."""

    id: UUID
    dataset_id: UUID
    field_name: str
    parent_id: UUID | None
    content: str
    author_id: UUID | None
    author_name: str | None
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[SchemaCommentResponse])
async def list_schema_comments(
    dataset_id: UUID,
    auth: AuthDep,
    db: DbDep,
    field_name: str | None = None,
) -> list[SchemaCommentResponse]:
    """List schema comments for a dataset."""
    comments = await db.list_schema_comments(
        tenant_id=auth.tenant_id,
        dataset_id=dataset_id,
        field_name=field_name,
    )
    return [SchemaCommentResponse(**c) for c in comments]


@router.post("", status_code=201, response_model=SchemaCommentResponse)
async def create_schema_comment(
    dataset_id: UUID,
    body: SchemaCommentCreate,
    auth: AuthDep,
    db: DbDep,
) -> SchemaCommentResponse:
    """Create a schema comment."""
    dataset = await db.get_dataset_by_id(auth.tenant_id, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    comment = await db.create_schema_comment(
        tenant_id=auth.tenant_id,
        dataset_id=dataset_id,
        field_name=body.field_name,
        content=body.content,
        parent_id=body.parent_id,
        author_id=auth.user_id,
        author_name=None,
    )
    return SchemaCommentResponse(**comment)


@router.patch("/{comment_id}", response_model=SchemaCommentResponse)
async def update_schema_comment(
    dataset_id: UUID,
    comment_id: UUID,
    body: SchemaCommentUpdate,
    auth: AuthDep,
    db: DbDep,
) -> SchemaCommentResponse:
    """Update a schema comment."""
    comment = await db.update_schema_comment(
        tenant_id=auth.tenant_id,
        comment_id=comment_id,
        content=body.content,
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment["dataset_id"] != dataset_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    return SchemaCommentResponse(**comment)


@router.delete("/{comment_id}", status_code=204)
async def delete_schema_comment(
    dataset_id: UUID,
    comment_id: UUID,
    auth: AuthDep,
    db: DbDep,
) -> None:
    """Delete a schema comment."""
    existing = await db.get_schema_comment(
        tenant_id=auth.tenant_id,
        comment_id=comment_id,
    )
    if not existing or existing["dataset_id"] != dataset_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    deleted = await db.delete_schema_comment(
        tenant_id=auth.tenant_id,
        comment_id=comment_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found")
