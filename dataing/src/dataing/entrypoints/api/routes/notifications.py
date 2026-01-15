"""Notifications routes for in-app notifications."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

logger = logging.getLogger(__name__)

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


@router.get("/stream")
async def notification_stream(
    request: Request,
    auth: AuthDep,
    app_db: AppDbDep,
    after: str | None = Query(
        default=None,
        description="Resume from notification ID (for reconnect)",
    ),
) -> EventSourceResponse:
    """Stream real-time notifications via Server-Sent Events.

    Browser EventSource can't send headers, so JWT is accepted via query param.
    The auth middleware already handles `?token=` for SSE endpoints.

    Events:
    - `notification`: New notification (includes cursor for resume)
    - `heartbeat`: Keep-alive every 30 seconds

    Example:
        GET /notifications/stream?token=<jwt>&after=<notification_id>

    Returns:
        EventSourceResponse with SSE stream.
    """
    user_id = _require_user_id(auth)
    tenant_id = auth.tenant_id

    # Parse after parameter if provided
    last_id: UUID | None = None
    if after:
        try:
            last_id = UUID(after)
        except ValueError:
            pass  # Invalid UUID, start from beginning

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        """Generate SSE events for notification updates."""
        nonlocal last_id
        last_heartbeat = datetime.now(UTC)
        poll_count = 0
        max_polls = 3600  # 30 minutes at 0.5s intervals

        try:
            while poll_count < max_polls:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info("SSE client disconnected")
                    break

                # Send heartbeat every 30 seconds
                now = datetime.now(UTC)
                if (now - last_heartbeat).total_seconds() >= 30:
                    yield {
                        "event": "heartbeat",
                        "data": to_json_string({"ts": now.isoformat()}),
                    }
                    last_heartbeat = now

                # Poll for new notifications
                try:
                    notifications = await app_db.get_new_notifications(
                        tenant_id=tenant_id,
                        since_id=last_id,
                        limit=50,
                    )

                    for n in notifications:
                        notification_data = {
                            "id": str(n["id"]),
                            "type": n["type"],
                            "title": n["title"],
                            "body": n.get("body"),
                            "resource_kind": n.get("resource_kind"),
                            "resource_id": str(n["resource_id"]) if n.get("resource_id") else None,
                            "severity": n["severity"],
                            "created_at": n["created_at"].isoformat(),
                        }
                        yield {
                            "event": "notification",
                            "id": str(n["id"]),  # For client-side Last-Event-ID
                            "data": to_json_string(notification_data),
                        }
                        last_id = n["id"]

                except Exception as e:
                    logger.error(f"Error polling notifications: {e}")
                    yield {
                        "event": "error",
                        "data": to_json_string({"error": "Failed to fetch notifications"}),
                    }

                await asyncio.sleep(0.5)
                poll_count += 1

            # Stream timeout
            if poll_count >= max_polls:
                yield {
                    "event": "timeout",
                    "data": to_json_string({"message": "Stream timeout, please reconnect"}),
                }

        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for user {user_id}")

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
