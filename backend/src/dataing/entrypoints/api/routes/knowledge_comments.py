"""API routes for knowledge comments."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from dataing.adapters.audit import audited
from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/datasets/{dataset_id}/knowledge-comments", tags=["knowledge-comments"])

AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
DbDep = Annotated[AppDatabase, Depends(get_app_db)]


class KnowledgeCommentCreate(BaseModel):
    """Request body for creating a knowledge comment."""

    content: str = Field(..., min_length=1)
    parent_id: UUID | None = None


class KnowledgeCommentUpdate(BaseModel):
    """Request body for updating a knowledge comment."""

    content: str = Field(..., min_length=1)


class KnowledgeCommentResponse(BaseModel):
    """Response for a knowledge comment."""

    id: UUID
    dataset_id: UUID
    parent_id: UUID | None
    content: str
    author_id: UUID | None
    author_name: str | None
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[KnowledgeCommentResponse])
async def list_knowledge_comments(
    dataset_id: UUID,
    auth: AuthDep,
    db: DbDep,
) -> list[KnowledgeCommentResponse]:
    """List knowledge comments for a dataset."""
    comments = await db.list_knowledge_comments(
        tenant_id=auth.tenant_id,
        dataset_id=dataset_id,
    )
    return [KnowledgeCommentResponse(**c) for c in comments]


@router.post("", status_code=201, response_model=KnowledgeCommentResponse)
@audited(action="knowledge_comment.create", resource_type="knowledge_comment")
async def create_knowledge_comment(
    dataset_id: UUID,
    body: KnowledgeCommentCreate,
    auth: AuthDep,
    db: DbDep,
) -> KnowledgeCommentResponse:
    """Create a knowledge comment."""
    dataset = await db.get_dataset_by_id(auth.tenant_id, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    comment = await db.create_knowledge_comment(
        tenant_id=auth.tenant_id,
        dataset_id=dataset_id,
        content=body.content,
        parent_id=body.parent_id,
        author_id=auth.user_id,
        author_name=None,
    )
    return KnowledgeCommentResponse(**comment)


@router.patch("/{comment_id}", response_model=KnowledgeCommentResponse)
@audited(action="knowledge_comment.update", resource_type="knowledge_comment")
async def update_knowledge_comment(
    dataset_id: UUID,
    comment_id: UUID,
    body: KnowledgeCommentUpdate,
    auth: AuthDep,
    db: DbDep,
) -> KnowledgeCommentResponse:
    """Update a knowledge comment."""
    comment = await db.update_knowledge_comment(
        tenant_id=auth.tenant_id,
        comment_id=comment_id,
        content=body.content,
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment["dataset_id"] != dataset_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    return KnowledgeCommentResponse(**comment)


@router.delete("/{comment_id}", status_code=204, response_class=Response)
@audited(action="knowledge_comment.delete", resource_type="knowledge_comment")
async def delete_knowledge_comment(
    dataset_id: UUID,
    comment_id: UUID,
    auth: AuthDep,
    db: DbDep,
) -> Response:
    """Delete a knowledge comment."""
    existing = await db.get_knowledge_comment(
        tenant_id=auth.tenant_id,
        comment_id=comment_id,
    )
    if not existing or existing["dataset_id"] != dataset_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    deleted = await db.delete_knowledge_comment(
        tenant_id=auth.tenant_id,
        comment_id=comment_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found")
    return Response(status_code=204)
