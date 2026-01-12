"""Notifications routes for in-app notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


class NotificationResponse(BaseModel):
    """Single notification response."""

    id: UUID
    type: str
    title: str
    body: str | None
    resource_kind: str | None
    resource_id: UUID | None
    severity: str
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(BaseModel):
    """Paginated notification list response."""

    items: list[NotificationResponse]
    next_cursor: str | None
    has_more: bool


class UnreadCountResponse(BaseModel):
    """Unread notification count response."""

    count: int


class MarkAllReadResponse(BaseModel):
    """Response after marking all notifications as read."""

    marked_count: int
    cursor: str | None = Field(
        default=None,
        description="Cursor pointing to newest marked notification for resumability",
    )


def _require_user_id(auth: ApiKeyContext) -> UUID:
    """Require user_id to be present in auth context.

    Notifications are per-user, so we need a user identity.
    JWT auth always provides this. API keys can optionally be tied to a user.
    """
    user_id: UUID | None = auth.user_id
    if user_id is None:
        raise HTTPException(
            status_code=403,
            detail="User identity required. Use JWT authentication or a user-scoped API key.",
        )
    result: UUID = user_id
    return result


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    auth: AuthDep,
    app_db: AppDbDep,
    limit: int = Query(default=50, ge=1, le=100, description="Max notifications to return"),
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    unread_only: bool = Query(default=False, description="Only return unread notifications"),
) -> NotificationListResponse:
    """List notifications for the current user.

    Uses cursor-based pagination for efficient traversal.
    Cursor format: base64(created_at|id)
    """
    user_id = _require_user_id(auth)

    items, next_cursor, has_more = await app_db.list_notifications(
        tenant_id=auth.tenant_id,
        user_id=user_id,
        limit=limit,
        cursor=cursor,
        unread_only=unread_only,
    )

    return NotificationListResponse(
        items=[NotificationResponse(**item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.put("/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> None:
    """Mark a notification as read.

    Idempotent - returns 204 even if already read.
    Returns 404 if notification doesn't exist or belongs to another tenant.
    """
    user_id = _require_user_id(auth)

    success = await app_db.mark_notification_read(
        notification_id=notification_id,
        user_id=user_id,
        tenant_id=auth.tenant_id,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")


@router.post("/read-all", response_model=MarkAllReadResponse)
async def mark_all_notifications_read(
    auth: AuthDep,
    app_db: AppDbDep,
) -> MarkAllReadResponse:
    """Mark all notifications as read for the current user.

    Returns count of notifications marked and a cursor pointing to
    the newest marked notification for resumability.
    """
    user_id = _require_user_id(auth)

    count, cursor = await app_db.mark_all_notifications_read(
        tenant_id=auth.tenant_id,
        user_id=user_id,
    )

    return MarkAllReadResponse(marked_count=count, cursor=cursor)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    auth: AuthDep,
    app_db: AppDbDep,
) -> UnreadCountResponse:
    """Get count of unread notifications for the current user."""
    user_id = _require_user_id(auth)

    count = await app_db.get_unread_notification_count(
        tenant_id=auth.tenant_id,
        user_id=user_id,
    )

    return UnreadCountResponse(count=count)
