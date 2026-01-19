"""API routes for Issues CRUD operations.

This module provides endpoints for creating, reading, updating, and listing
issues with state machine enforcement and cursor-based pagination.
"""

from __future__ import annotations

import asyncio
import base64
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
from dataing.models.issue import IssueStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/issues", tags=["issues"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


# ============================================================================
# State Machine
# ============================================================================

# Valid state transitions: from_state -> set of valid to_states
STATE_TRANSITIONS: dict[str, set[str]] = {
    IssueStatus.OPEN.value: {IssueStatus.TRIAGED.value, IssueStatus.CLOSED.value},
    IssueStatus.TRIAGED.value: {
        IssueStatus.IN_PROGRESS.value,
        IssueStatus.BLOCKED.value,
        IssueStatus.CLOSED.value,
    },
    IssueStatus.IN_PROGRESS.value: {
        IssueStatus.BLOCKED.value,
        IssueStatus.RESOLVED.value,
        IssueStatus.CLOSED.value,
    },
    IssueStatus.BLOCKED.value: {
        IssueStatus.IN_PROGRESS.value,
        IssueStatus.RESOLVED.value,
        IssueStatus.CLOSED.value,
    },
    IssueStatus.RESOLVED.value: {IssueStatus.CLOSED.value, IssueStatus.OPEN.value},
    IssueStatus.CLOSED.value: {IssueStatus.OPEN.value},  # reopening
}


def validate_state_transition(
    current_status: str,
    new_status: str,
    assignee_user_id: UUID | None,
    acknowledged_by: UUID | None,
    resolution_note: str | None,
    has_linked_investigation: bool = False,
) -> tuple[bool, str]:
    """Validate an issue state transition.

    Args:
        current_status: Current issue status.
        new_status: Requested new status.
        assignee_user_id: Currently assigned user.
        acknowledged_by: User who acknowledged (for triage without assignee).
        resolution_note: Resolution note text.
        has_linked_investigation: Whether issue has a linked investigation.

    Returns:
        Tuple of (is_valid, error_message).
    """
    # Check if transition is allowed
    valid_transitions = STATE_TRANSITIONS.get(current_status, set())
    if new_status not in valid_transitions:
        return False, f"Cannot transition from {current_status} to {new_status}"

    # Transitions to IN_PROGRESS or BLOCKED require assignee OR acknowledged_by
    if new_status in {IssueStatus.IN_PROGRESS.value, IssueStatus.BLOCKED.value}:
        if not assignee_user_id and not acknowledged_by:
            return (
                False,
                f"Transition to {new_status} requires an assignee or acknowledged_by user",
            )

    # Transition to RESOLVED requires resolution_note OR linked investigation
    if new_status == IssueStatus.RESOLVED.value:
        if not resolution_note and not has_linked_investigation:
            return (
                False,
                "Transition to RESOLVED requires resolution_note or a linked investigation",
            )

    return True, ""


# ============================================================================
# Pydantic Schemas
# ============================================================================


class IssueCreate(BaseModel):
    """Request body for creating an issue."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: str | None = Field(None, pattern="^P[0-3]$")
    severity: str | None = Field(None, pattern="^(low|medium|high|critical)$")
    dataset_id: str | None = None
    labels: list[str] = Field(default_factory=list)


class IssueUpdate(BaseModel):
    """Request body for updating an issue."""

    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    status: str | None = Field(None, pattern="^(open|triaged|in_progress|blocked|resolved|closed)$")
    priority: str | None = Field(None, pattern="^P[0-3]$")
    severity: str | None = Field(None, pattern="^(low|medium|high|critical)$")
    assignee_user_id: UUID | None = None
    acknowledged_by: UUID | None = None
    resolution_note: str | None = None
    labels: list[str] | None = None


class IssueResponse(BaseModel):
    """Single issue response."""

    id: UUID
    number: int
    title: str
    description: str | None
    status: str
    priority: str | None
    severity: str | None
    dataset_id: str | None
    assignee_user_id: UUID | None
    acknowledged_by: UUID | None
    created_by_user_id: UUID | None
    author_type: str
    source_provider: str | None
    source_external_id: str | None
    source_external_url: str | None
    resolution_note: str | None
    labels: list[str]
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class IssueRedactedResponse(BaseModel):
    """Redacted issue response for users without dataset permission."""

    id: UUID
    number: int
    title: str
    status: str


class IssueListResponse(BaseModel):
    """Paginated issue list response."""

    items: list[IssueResponse]
    next_cursor: str | None
    has_more: bool
    total: int


# ============================================================================
# Helper Functions
# ============================================================================


def _encode_cursor(created_at: datetime, issue_id: UUID) -> str:
    """Encode pagination cursor."""
    payload = f"{created_at.isoformat()}|{issue_id}"
    return base64.b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID] | None:
    """Decode pagination cursor."""
    try:
        decoded = base64.b64decode(cursor).decode()
        parts = decoded.split("|")
        return datetime.fromisoformat(parts[0]), UUID(parts[1])
    except (ValueError, IndexError):
        return None


async def _get_issue_labels(db: AppDatabase, issue_id: UUID) -> list[str]:
    """Get labels for an issue."""
    rows = await db.fetch_all(
        "SELECT label FROM issue_labels WHERE issue_id = $1 ORDER BY label",
        issue_id,
    )
    return [row["label"] for row in rows]


async def _set_issue_labels(db: AppDatabase, issue_id: UUID, labels: list[str]) -> None:
    """Set labels for an issue (replaces existing)."""
    await db.execute("DELETE FROM issue_labels WHERE issue_id = $1", issue_id)
    for label in labels:
        await db.execute(
            "INSERT INTO issue_labels (issue_id, label) VALUES ($1, $2)",
            issue_id,
            label,
        )


async def _has_linked_investigation(db: AppDatabase, issue_id: UUID) -> bool:
    """Check if issue has a linked investigation with synthesis."""
    row = await db.fetch_one(
        """
        SELECT 1 FROM issue_investigation_runs
        WHERE issue_id = $1 AND synthesis_summary IS NOT NULL
        LIMIT 1
        """,
        issue_id,
    )
    return row is not None


async def _record_issue_event(
    db: AppDatabase,
    issue_id: UUID,
    event_type: str,
    actor_user_id: UUID | None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Record an issue event."""
    await db.execute(
        """
        INSERT INTO issue_events (issue_id, event_type, actor_user_id, payload)
        VALUES ($1, $2, $3, $4)
        """,
        issue_id,
        event_type,
        actor_user_id,
        to_json_string(payload or {}),
    )


# ============================================================================
# API Routes
# ============================================================================


@router.get("", response_model=IssueListResponse)
async def list_issues(
    auth: AuthDep,
    db: AppDbDep,
    status: str | None = Query(default=None, description="Filter by status"),  # noqa: B008
    priority: str | None = Query(default=None, description="Filter by priority"),  # noqa: B008
    severity: str | None = Query(default=None, description="Filter by severity"),  # noqa: B008
    assignee: UUID | None = Query(default=None, description="Filter by assignee"),  # noqa: B008
    search: str | None = Query(default=None, description="Full-text search"),  # noqa: B008
    cursor: str | None = Query(default=None, description="Pagination cursor"),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=100, description="Max issues"),  # noqa: B008
) -> IssueListResponse:
    """List issues with filters and cursor-based pagination.

    Uses cursor-based pagination with base64(updated_at|id) format.
    Returns issues ordered by updated_at descending.
    """
    # Cap limit
    limit = min(limit, 100)

    # Parse cursor
    cursor_data = _decode_cursor(cursor) if cursor else None

    # Build query parts
    conditions = ["tenant_id = $1"]
    params: list[Any] = [auth.tenant_id]
    param_idx = 2

    if status:
        conditions.append(f"status = ${param_idx}")
        params.append(status)
        param_idx += 1

    if priority:
        conditions.append(f"priority = ${param_idx}")
        params.append(priority)
        param_idx += 1

    if severity:
        conditions.append(f"severity = ${param_idx}")
        params.append(severity)
        param_idx += 1

    if assignee:
        conditions.append(f"assignee_user_id = ${param_idx}")
        params.append(assignee)
        param_idx += 1

    if search:
        conditions.append(f"search_vector @@ plainto_tsquery('english', ${param_idx})")
        params.append(search)
        param_idx += 1

    if cursor_data:
        cursor_updated_at, cursor_id = cursor_data
        conditions.append(f"(updated_at, id) < (${param_idx}, ${param_idx + 1})")
        params.extend([cursor_updated_at, cursor_id])
        param_idx += 2

    where_clause = " AND ".join(conditions)

    # Get total count (without cursor/limit)
    count_conditions = [c for c in conditions if "updated_at, id" not in c]
    count_where = " AND ".join(count_conditions)
    count_params = params[: len(count_conditions)]

    count_row = await db.fetch_one(
        f"SELECT COUNT(*) as count FROM issues WHERE {count_where}",
        *count_params,
    )
    total = count_row["count"] if count_row else 0

    # Fetch issues
    query = f"""
        SELECT id, number, title, description, status, priority, severity,
               dataset_id, assignee_user_id, acknowledged_by, created_by_user_id,
               author_type, source_provider, source_external_id, source_external_url,
               resolution_note, created_at, updated_at, closed_at
        FROM issues
        WHERE {where_clause}
        ORDER BY updated_at DESC, id DESC
        LIMIT ${param_idx}
    """
    params.append(limit + 1)  # Fetch one extra to check has_more

    rows = await db.fetch_all(query, *params)

    # Determine has_more
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    # Build response items with labels
    items = []
    for row in rows:
        labels = await _get_issue_labels(db, row["id"])
        items.append(
            IssueResponse(
                id=row["id"],
                number=row["number"],
                title=row["title"],
                description=row["description"],
                status=row["status"],
                priority=row["priority"],
                severity=row["severity"],
                dataset_id=row["dataset_id"],
                assignee_user_id=row["assignee_user_id"],
                acknowledged_by=row["acknowledged_by"],
                created_by_user_id=row["created_by_user_id"],
                author_type=row["author_type"],
                source_provider=row["source_provider"],
                source_external_id=row["source_external_id"],
                source_external_url=row["source_external_url"],
                resolution_note=row["resolution_note"],
                labels=labels,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                closed_at=row["closed_at"],
            )
        )

    # Build next cursor
    next_cursor = None
    if has_more and rows:
        last_row = rows[-1]
        next_cursor = _encode_cursor(last_row["updated_at"], last_row["id"])

    return IssueListResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total=total,
    )


@router.post("", response_model=IssueResponse, status_code=201)
async def create_issue(
    auth: AuthDep,
    db: AppDbDep,
    body: IssueCreate,
) -> IssueResponse:
    """Create a new issue.

    Issues are created in OPEN status. Number is auto-assigned per-tenant.
    """
    # Get next issue number
    number_row = await db.fetch_one(
        "SELECT next_issue_number($1) as number",
        auth.tenant_id,
    )
    number = number_row["number"] if number_row else 1

    # Insert issue
    row = await db.execute_returning(
        """
        INSERT INTO issues (
            tenant_id, number, title, description, status, priority, severity,
            dataset_id, created_by_user_id, author_type
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id, number, title, description, status, priority, severity,
                  dataset_id, assignee_user_id, acknowledged_by, created_by_user_id,
                  author_type, source_provider, source_external_id, source_external_url,
                  resolution_note, created_at, updated_at, closed_at
        """,
        auth.tenant_id,
        number,
        body.title,
        body.description,
        IssueStatus.OPEN.value,
        body.priority,
        body.severity,
        body.dataset_id,
        auth.user_id,
        "human",
    )

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create issue")

    issue_id = row["id"]

    # Set labels
    if body.labels:
        await _set_issue_labels(db, issue_id, body.labels)

    # Record creation event
    await _record_issue_event(
        db,
        issue_id,
        "created",
        auth.user_id,
        {"title": body.title},
    )

    labels = await _get_issue_labels(db, issue_id)

    return IssueResponse(
        id=row["id"],
        number=row["number"],
        title=row["title"],
        description=row["description"],
        status=row["status"],
        priority=row["priority"],
        severity=row["severity"],
        dataset_id=row["dataset_id"],
        assignee_user_id=row["assignee_user_id"],
        acknowledged_by=row["acknowledged_by"],
        created_by_user_id=row["created_by_user_id"],
        author_type=row["author_type"],
        source_provider=row["source_provider"],
        source_external_id=row["source_external_id"],
        source_external_url=row["source_external_url"],
        resolution_note=row["resolution_note"],
        labels=labels,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        closed_at=row["closed_at"],
    )


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(
    issue_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> IssueResponse:
    """Get issue by ID.

    Returns the full issue if user has access, 404 if not found.
    """
    row = await db.fetch_one(
        """
        SELECT id, number, title, description, status, priority, severity,
               dataset_id, assignee_user_id, acknowledged_by, created_by_user_id,
               author_type, source_provider, source_external_id, source_external_url,
               resolution_note, created_at, updated_at, closed_at
        FROM issues
        WHERE id = $1 AND tenant_id = $2
        """,
        issue_id,
        auth.tenant_id,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")

    labels = await _get_issue_labels(db, issue_id)

    return IssueResponse(
        id=row["id"],
        number=row["number"],
        title=row["title"],
        description=row["description"],
        status=row["status"],
        priority=row["priority"],
        severity=row["severity"],
        dataset_id=row["dataset_id"],
        assignee_user_id=row["assignee_user_id"],
        acknowledged_by=row["acknowledged_by"],
        created_by_user_id=row["created_by_user_id"],
        author_type=row["author_type"],
        source_provider=row["source_provider"],
        source_external_id=row["source_external_id"],
        source_external_url=row["source_external_url"],
        resolution_note=row["resolution_note"],
        labels=labels,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        closed_at=row["closed_at"],
    )


@router.patch("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
    body: IssueUpdate,
) -> IssueResponse:
    """Update issue fields.

    Enforces state machine transitions when status is changed.
    """
    # Get current issue
    current = await db.fetch_one(
        """
        SELECT id, status, assignee_user_id, acknowledged_by, resolution_note
        FROM issues
        WHERE id = $1 AND tenant_id = $2
        """,
        issue_id,
        auth.tenant_id,
    )

    if not current:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Handle status transition
    if body.status and body.status != current["status"]:
        # Determine effective values for validation
        assignee = (
            body.assignee_user_id
            if body.assignee_user_id is not None
            else current["assignee_user_id"]
        )
        acknowledged = (
            body.acknowledged_by if body.acknowledged_by is not None else current["acknowledged_by"]
        )
        resolution = (
            body.resolution_note if body.resolution_note is not None else current["resolution_note"]
        )
        has_investigation = await _has_linked_investigation(db, issue_id)

        is_valid, error = validate_state_transition(
            current["status"],
            body.status,
            assignee,
            acknowledged,
            resolution,
            has_investigation,
        )

        if not is_valid:
            raise HTTPException(status_code=400, detail=error)

    # Build update query dynamically
    updates = []
    params: list[Any] = []
    param_idx = 1

    if body.title is not None:
        updates.append(f"title = ${param_idx}")
        params.append(body.title)
        param_idx += 1

    if body.description is not None:
        updates.append(f"description = ${param_idx}")
        params.append(body.description)
        param_idx += 1

    if body.status is not None:
        updates.append(f"status = ${param_idx}")
        params.append(body.status)
        param_idx += 1

        # Set closed_at when transitioning to CLOSED
        if body.status == IssueStatus.CLOSED.value:
            updates.append(f"closed_at = ${param_idx}")
            params.append(datetime.now(UTC))
            param_idx += 1
        elif current["status"] == IssueStatus.CLOSED.value:
            # Clear closed_at when reopening
            updates.append("closed_at = NULL")

    if body.priority is not None:
        updates.append(f"priority = ${param_idx}")
        params.append(body.priority)
        param_idx += 1

    if body.severity is not None:
        updates.append(f"severity = ${param_idx}")
        params.append(body.severity)
        param_idx += 1

    if body.assignee_user_id is not None:
        updates.append(f"assignee_user_id = ${param_idx}")
        params.append(body.assignee_user_id)
        param_idx += 1

    if body.acknowledged_by is not None:
        updates.append(f"acknowledged_by = ${param_idx}")
        params.append(body.acknowledged_by)
        param_idx += 1

    if body.resolution_note is not None:
        updates.append(f"resolution_note = ${param_idx}")
        params.append(body.resolution_note)
        param_idx += 1

    if not updates:
        # Nothing to update, just return current issue
        return await get_issue(issue_id, auth, db)

    # Always update updated_at
    updates.append(f"updated_at = ${param_idx}")
    params.append(datetime.now(UTC))
    param_idx += 1

    # Add WHERE clause params
    params.extend([issue_id, auth.tenant_id])

    query = f"""
        UPDATE issues
        SET {', '.join(updates)}
        WHERE id = ${param_idx} AND tenant_id = ${param_idx + 1}
        RETURNING id, number, title, description, status, priority, severity,
                  dataset_id, assignee_user_id, acknowledged_by, created_by_user_id,
                  author_type, source_provider, source_external_id, source_external_url,
                  resolution_note, created_at, updated_at, closed_at
    """

    row = await db.execute_returning(query, *params)

    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Handle labels separately
    if body.labels is not None:
        await _set_issue_labels(db, issue_id, body.labels)

    # Record status change event
    if body.status and body.status != current["status"]:
        await _record_issue_event(
            db,
            issue_id,
            "status_changed",
            auth.user_id,
            {"from": current["status"], "to": body.status},
        )

    # Record assignment event
    if body.assignee_user_id and body.assignee_user_id != current["assignee_user_id"]:
        await _record_issue_event(
            db,
            issue_id,
            "assigned",
            auth.user_id,
            {"assignee_user_id": str(body.assignee_user_id)},
        )

    labels = await _get_issue_labels(db, issue_id)

    return IssueResponse(
        id=row["id"],
        number=row["number"],
        title=row["title"],
        description=row["description"],
        status=row["status"],
        priority=row["priority"],
        severity=row["severity"],
        dataset_id=row["dataset_id"],
        assignee_user_id=row["assignee_user_id"],
        acknowledged_by=row["acknowledged_by"],
        created_by_user_id=row["created_by_user_id"],
        author_type=row["author_type"],
        source_provider=row["source_provider"],
        source_external_id=row["source_external_id"],
        source_external_url=row["source_external_url"],
        resolution_note=row["resolution_note"],
        labels=labels,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        closed_at=row["closed_at"],
    )


# ============================================================================
# Comment Schemas
# ============================================================================


class IssueCommentCreate(BaseModel):
    """Request body for creating an issue comment."""

    body: str = Field(..., min_length=1)


class IssueCommentResponse(BaseModel):
    """Response for an issue comment."""

    id: UUID
    issue_id: UUID
    author_user_id: UUID
    body: str
    created_at: datetime
    updated_at: datetime


class IssueCommentListResponse(BaseModel):
    """Paginated comment list response."""

    items: list[IssueCommentResponse]
    total: int


# ============================================================================
# Event Schemas
# ============================================================================


class IssueEventResponse(BaseModel):
    """Response for an issue event."""

    id: UUID
    issue_id: UUID
    event_type: str
    actor_user_id: UUID | None
    payload: dict[str, Any]
    created_at: datetime


class IssueEventListResponse(BaseModel):
    """Paginated event list response."""

    items: list[IssueEventResponse]
    total: int
    next_cursor: str | None = None


# ============================================================================
# Watcher Schemas
# ============================================================================


class WatcherResponse(BaseModel):
    """Response for a watcher."""

    user_id: UUID
    created_at: datetime


class WatcherListResponse(BaseModel):
    """Watcher list response."""

    items: list[WatcherResponse]
    total: int


# ============================================================================
# Comment Helper Functions
# ============================================================================


async def _verify_issue_access(
    db: AppDatabase,
    issue_id: UUID,
    tenant_id: UUID,
) -> dict[str, Any]:
    """Verify issue exists and belongs to tenant.

    Returns the issue row or raises HTTPException.
    """
    row = await db.fetch_one(
        "SELECT id, tenant_id FROM issues WHERE id = $1 AND tenant_id = $2",
        issue_id,
        tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")
    result: dict[str, Any] = row
    return result


# ============================================================================
# Comment API Routes
# ============================================================================


@router.get("/{issue_id}/comments", response_model=IssueCommentListResponse)
async def list_issue_comments(
    issue_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> IssueCommentListResponse:
    """List comments for an issue."""
    await _verify_issue_access(db, issue_id, auth.tenant_id)

    rows = await db.fetch_all(
        """
        SELECT id, issue_id, author_user_id, body, created_at, updated_at
        FROM issue_comments
        WHERE issue_id = $1
        ORDER BY created_at ASC
        """,
        issue_id,
    )

    items = [
        IssueCommentResponse(
            id=row["id"],
            issue_id=row["issue_id"],
            author_user_id=row["author_user_id"],
            body=row["body"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]

    return IssueCommentListResponse(items=items, total=len(items))


@router.post("/{issue_id}/comments", response_model=IssueCommentResponse, status_code=201)
async def create_issue_comment(
    issue_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
    body: IssueCommentCreate,
) -> IssueCommentResponse:
    """Add a comment to an issue.

    Requires user identity (JWT auth or user-scoped API key).
    """
    await _verify_issue_access(db, issue_id, auth.tenant_id)

    if auth.user_id is None:
        raise HTTPException(
            status_code=403,
            detail="User identity required to create comments",
        )

    row = await db.execute_returning(
        """
        INSERT INTO issue_comments (issue_id, author_user_id, body)
        VALUES ($1, $2, $3)
        RETURNING id, issue_id, author_user_id, body, created_at, updated_at
        """,
        issue_id,
        auth.user_id,
        body.body,
    )

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create comment")

    # Record comment_added event
    await _record_issue_event(
        db,
        issue_id,
        "comment_added",
        auth.user_id,
        {"comment_id": str(row["id"])},
    )

    # Update issue updated_at timestamp
    await db.execute(
        "UPDATE issues SET updated_at = NOW() WHERE id = $1",
        issue_id,
    )

    return IssueCommentResponse(
        id=row["id"],
        issue_id=row["issue_id"],
        author_user_id=row["author_user_id"],
        body=row["body"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ============================================================================
# Watcher API Routes
# ============================================================================


@router.get("/{issue_id}/watchers", response_model=WatcherListResponse)
async def list_issue_watchers(
    issue_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> WatcherListResponse:
    """List watchers for an issue."""
    await _verify_issue_access(db, issue_id, auth.tenant_id)

    rows = await db.fetch_all(
        """
        SELECT user_id, created_at
        FROM issue_watchers
        WHERE issue_id = $1
        ORDER BY created_at ASC
        """,
        issue_id,
    )

    items = [WatcherResponse(user_id=row["user_id"], created_at=row["created_at"]) for row in rows]

    return WatcherListResponse(items=items, total=len(items))


@router.post("/{issue_id}/watch", status_code=204)
async def add_issue_watcher(
    issue_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> None:
    """Subscribe the current user as a watcher.

    Idempotent - returns 204 even if already watching.
    Requires user identity (JWT auth or user-scoped API key).
    """
    await _verify_issue_access(db, issue_id, auth.tenant_id)

    if auth.user_id is None:
        raise HTTPException(
            status_code=403,
            detail="User identity required to watch issues",
        )

    # Upsert watcher (idempotent)
    await db.execute(
        """
        INSERT INTO issue_watchers (issue_id, user_id)
        VALUES ($1, $2)
        ON CONFLICT (issue_id, user_id) DO NOTHING
        """,
        issue_id,
        auth.user_id,
    )


@router.delete("/{issue_id}/watch", status_code=204)
async def remove_issue_watcher(
    issue_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> None:
    """Unsubscribe the current user as a watcher.

    Idempotent - returns 204 even if not watching.
    Requires user identity (JWT auth or user-scoped API key).
    """
    await _verify_issue_access(db, issue_id, auth.tenant_id)

    if auth.user_id is None:
        raise HTTPException(
            status_code=403,
            detail="User identity required to unwatch issues",
        )

    await db.execute(
        "DELETE FROM issue_watchers WHERE issue_id = $1 AND user_id = $2",
        issue_id,
        auth.user_id,
    )


# ============================================================================
# Investigation Run Schemas
# ============================================================================


class InvestigationRunCreate(BaseModel):
    """Request body for spawning an investigation from an issue."""

    focus_prompt: str = Field(..., min_length=1)
    dataset_id: str | None = None  # Inherits from issue if not provided
    execution_profile: str = Field(
        default="standard",
        pattern="^(safe|standard|deep)$",
    )


class InvestigationRunResponse(BaseModel):
    """Response for an investigation run."""

    id: UUID
    issue_id: UUID
    investigation_id: UUID
    trigger_type: str
    focus_prompt: str | None
    execution_profile: str
    approval_status: str | None
    confidence: float | None
    root_cause_tag: str | None
    synthesis_summary: str | None
    created_at: datetime
    completed_at: datetime | None


class InvestigationRunListResponse(BaseModel):
    """Paginated investigation run list response."""

    items: list[InvestigationRunResponse]
    total: int


# ============================================================================
# Investigation Run API Routes
# ============================================================================


@router.get("/{issue_id}/investigation-runs", response_model=InvestigationRunListResponse)
async def list_investigation_runs(
    issue_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> InvestigationRunListResponse:
    """List investigation runs for an issue."""
    await _verify_issue_access(db, issue_id, auth.tenant_id)

    rows = await db.fetch_all(
        """
        SELECT id, issue_id, investigation_id, trigger_type, focus_prompt,
               execution_profile, approval_status, confidence, root_cause_tag,
               synthesis_summary, created_at, completed_at
        FROM issue_investigation_runs
        WHERE issue_id = $1
        ORDER BY created_at DESC
        """,
        issue_id,
    )

    items = [
        InvestigationRunResponse(
            id=row["id"],
            issue_id=row["issue_id"],
            investigation_id=row["investigation_id"],
            trigger_type=row["trigger_type"],
            focus_prompt=row["focus_prompt"],
            execution_profile=row["execution_profile"],
            approval_status=row["approval_status"],
            confidence=row["confidence"],
            root_cause_tag=row["root_cause_tag"],
            synthesis_summary=row["synthesis_summary"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
        for row in rows
    ]

    return InvestigationRunListResponse(items=items, total=len(items))


@router.post(
    "/{issue_id}/investigation-runs",
    response_model=InvestigationRunResponse,
    status_code=201,
)
async def spawn_investigation(
    issue_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
    body: InvestigationRunCreate,
) -> InvestigationRunResponse:
    """Spawn an investigation from an issue.

    Creates a new investigation linked to this issue. The focus_prompt
    guides the investigation direction.

    Requires user identity (JWT auth or user-scoped API key).
    Deep profile may require approval depending on tenant settings.
    """
    # Verify issue exists and get its data
    issue = await db.fetch_one(
        """
        SELECT id, tenant_id, dataset_id
        FROM issues
        WHERE id = $1 AND tenant_id = $2
        """,
        issue_id,
        auth.tenant_id,
    )

    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    if auth.user_id is None:
        raise HTTPException(
            status_code=403,
            detail="User identity required to spawn investigations",
        )

    # Use dataset_id from request or inherit from issue
    dataset_id = body.dataset_id or issue["dataset_id"]

    if not dataset_id:
        raise HTTPException(
            status_code=400,
            detail="dataset_id required - not set on issue and not provided in request",
        )

    # Determine approval_status based on execution_profile
    # Deep profile may require approval - for now we approve immediately
    approval_status = None
    if body.execution_profile == "deep":
        approval_status = "approved"  # Could be "queued" based on tenant settings

    # Create a placeholder investigation record
    # In a real implementation, this would call the InvestigationService
    investigation_row = await db.execute_returning(
        """
        INSERT INTO investigations (tenant_id, alert, created_by_user_id)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        auth.tenant_id,
        '{"dataset_id": "' + dataset_id + '", "source": "issue_spawn"}',
        auth.user_id,
    )

    if not investigation_row:
        raise HTTPException(status_code=500, detail="Failed to create investigation")

    investigation_id = investigation_row["id"]

    # Create the issue_investigation_run record
    trigger_ref = {"user_id": str(auth.user_id), "dataset_id": dataset_id}

    row = await db.execute_returning(
        """
        INSERT INTO issue_investigation_runs (
            issue_id, investigation_id, trigger_type, trigger_ref,
            focus_prompt, execution_profile, approval_status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, issue_id, investigation_id, trigger_type, focus_prompt,
                  execution_profile, approval_status, confidence, root_cause_tag,
                  synthesis_summary, created_at, completed_at
        """,
        issue_id,
        investigation_id,
        "human",
        to_json_string(trigger_ref),
        body.focus_prompt,
        body.execution_profile,
        approval_status,
    )

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create investigation run")

    # Record investigation_spawned event
    await _record_issue_event(
        db,
        issue_id,
        "investigation_spawned",
        auth.user_id,
        {
            "investigation_id": str(investigation_id),
            "run_id": str(row["id"]),
            "focus_prompt": body.focus_prompt,
            "execution_profile": body.execution_profile,
        },
    )

    # Update issue updated_at timestamp
    await db.execute(
        "UPDATE issues SET updated_at = NOW() WHERE id = $1",
        issue_id,
    )

    return InvestigationRunResponse(
        id=row["id"],
        issue_id=row["issue_id"],
        investigation_id=row["investigation_id"],
        trigger_type=row["trigger_type"],
        focus_prompt=row["focus_prompt"],
        execution_profile=row["execution_profile"],
        approval_status=row["approval_status"],
        confidence=row["confidence"],
        root_cause_tag=row["root_cause_tag"],
        synthesis_summary=row["synthesis_summary"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


# ============================================================================
# Event Timeline API Routes
# ============================================================================


@router.get("/{issue_id}/events", response_model=IssueEventListResponse)
async def list_issue_events(
    issue_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,  # noqa: B008
    cursor: str | None = None,  # noqa: B008
) -> IssueEventListResponse:
    """List events for an issue (activity timeline).

    Returns events in reverse chronological order (newest first).
    Supports cursor-based pagination.
    """
    await _verify_issue_access(db, issue_id, auth.tenant_id)

    # Decode cursor if provided
    after_ts: datetime | None = None
    after_id: UUID | None = None
    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            after_ts, after_id = decoded

    # Build query with cursor pagination
    if after_ts and after_id:
        query = """
            SELECT id, issue_id, event_type, actor_user_id, payload, created_at
            FROM issue_events
            WHERE issue_id = $1
              AND (created_at, id) < ($2, $3)
            ORDER BY created_at DESC, id DESC
            LIMIT $4
        """
        rows = await db.fetch_all(query, issue_id, after_ts, after_id, limit + 1)
    else:
        query = """
            SELECT id, issue_id, event_type, actor_user_id, payload, created_at
            FROM issue_events
            WHERE issue_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2
        """
        rows = await db.fetch_all(query, issue_id, limit + 1)

    # Determine if there are more results
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    # Build response
    items = [
        IssueEventResponse(
            id=row["id"],
            issue_id=row["issue_id"],
            event_type=row["event_type"],
            actor_user_id=row["actor_user_id"],
            payload=row["payload"] if isinstance(row["payload"], dict) else {},
            created_at=row["created_at"],
        )
        for row in rows
    ]

    # Get total count
    count_row = await db.fetch_one(
        "SELECT COUNT(*) as cnt FROM issue_events WHERE issue_id = $1",
        issue_id,
    )
    total = count_row["cnt"] if count_row else 0

    # Build next cursor
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return IssueEventListResponse(
        items=items,
        total=total,
        next_cursor=next_cursor,
    )


# ============================================================================
# SSE Streaming
# ============================================================================


@router.get("/{issue_id}/stream")
async def stream_issue_events(
    issue_id: UUID,
    request: Request,
    auth: AuthDep,
    db: AppDbDep,
    after: str | None = None,  # noqa: B008
) -> EventSourceResponse:
    """Stream real-time issue updates via Server-Sent Events.

    Delivers events as they occur:
    - status_changed, assigned, comment_added, label_added/removed
    - investigation_spawned, investigation_completed

    The `after` parameter accepts an event ID to resume from.
    Sends heartbeat every 30 seconds to prevent connection timeout.
    """
    await _verify_issue_access(db, issue_id, auth.tenant_id)

    # Parse after parameter to get last event ID
    last_id: UUID | None = None
    if after:
        try:
            last_id = UUID(after)
        except ValueError:
            pass  # Invalid UUID, start from beginning

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        """Generate SSE events for issue updates."""
        nonlocal last_id
        last_heartbeat = datetime.now(UTC)
        poll_count = 0
        max_polls = 3600  # 30 minutes at 0.5s intervals

        try:
            while poll_count < max_polls:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"SSE client disconnected for issue {issue_id}")
                    break

                # Send heartbeat every 30 seconds
                now = datetime.now(UTC)
                if (now - last_heartbeat).total_seconds() >= 30:
                    yield {
                        "event": "heartbeat",
                        "data": to_json_string({"ts": now.isoformat()}),
                    }
                    last_heartbeat = now

                # Poll for new events
                try:
                    if last_id:
                        query = """
                            SELECT id, issue_id, event_type, actor_user_id,
                                   payload, created_at
                            FROM issue_events
                            WHERE issue_id = $1 AND id > $2
                            ORDER BY created_at ASC, id ASC
                            LIMIT 50
                        """
                        rows = await db.fetch_all(query, issue_id, last_id)
                    else:
                        query = """
                            SELECT id, issue_id, event_type, actor_user_id,
                                   payload, created_at
                            FROM issue_events
                            WHERE issue_id = $1
                            ORDER BY created_at ASC, id ASC
                            LIMIT 50
                        """
                        rows = await db.fetch_all(query, issue_id)

                    for row in rows:
                        event_data = {
                            "id": str(row["id"]),
                            "issue_id": str(row["issue_id"]),
                            "event_type": row["event_type"],
                            "actor_user_id": (
                                str(row["actor_user_id"]) if row["actor_user_id"] else None
                            ),
                            "payload": (row["payload"] if isinstance(row["payload"], dict) else {}),
                            "created_at": row["created_at"].isoformat(),
                        }
                        yield {
                            "event": row["event_type"],
                            "id": str(row["id"]),  # For Last-Event-ID
                            "data": to_json_string(event_data),
                        }
                        last_id = row["id"]

                except Exception as e:
                    logger.error(f"Error polling issue events: {e}")
                    yield {
                        "event": "error",
                        "data": to_json_string({"error": "Failed to fetch events"}),
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
            logger.info(f"SSE stream cancelled for issue {issue_id}")

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
