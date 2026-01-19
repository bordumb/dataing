"""API routes for comment voting."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from dataing.adapters.audit import audited
from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/comments", tags=["comment-votes"])

AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
DbDep = Annotated[AppDatabase, Depends(get_app_db)]


class VoteCreate(BaseModel):
    """Request body for voting."""

    vote: Literal[1, -1] = Field(..., description="1 for upvote, -1 for downvote")


@router.post("/{comment_type}/{comment_id}/vote", status_code=204, response_class=Response)
@audited(action="comment.vote", resource_type="comment")
async def vote_on_comment(
    comment_type: Literal["schema", "knowledge"],
    comment_id: UUID,
    body: VoteCreate,
    auth: AuthDep,
    db: DbDep,
) -> Response:
    """Vote on a comment."""
    # Verify comment exists
    if comment_type == "schema":
        comment = await db.get_schema_comment(auth.tenant_id, comment_id)
    else:
        comment = await db.get_knowledge_comment(auth.tenant_id, comment_id)

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Use user_id from auth, or fall back to tenant_id for API key auth
    user_id = auth.user_id if auth.user_id else auth.tenant_id

    await db.upsert_comment_vote(
        tenant_id=auth.tenant_id,
        comment_type=comment_type,
        comment_id=comment_id,
        user_id=user_id,
        vote=body.vote,
    )
    return Response(status_code=204)


@router.delete("/{comment_type}/{comment_id}/vote", status_code=204, response_class=Response)
@audited(action="comment.unvote", resource_type="comment")
async def remove_vote(
    comment_type: Literal["schema", "knowledge"],
    comment_id: UUID,
    auth: AuthDep,
    db: DbDep,
) -> Response:
    """Remove vote from a comment."""
    user_id = auth.user_id if auth.user_id else auth.tenant_id

    deleted = await db.delete_comment_vote(
        tenant_id=auth.tenant_id,
        comment_type=comment_type,
        comment_id=comment_id,
        user_id=user_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Vote not found")
    return Response(status_code=204)
