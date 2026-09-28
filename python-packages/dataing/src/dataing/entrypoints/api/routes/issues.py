"""API routes for Issues CRUD operations.

This module provides endpoints for creating, reading, updating, and listing
issues with state machine enforcement and cursor-based pagination.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sse_starlette.sse import EventSourceResponse

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issues import (
    ISSUE_COLUMNS,
    list_runs,
    open_issue,
    record_issue_event,
)
from dataing.core.investigation.brief import InvestigationBrief
from dataing.core.json_utils import to_json_safe, to_json_string
from dataing.entrypoints.api.deps import (
    get_app_db,
    get_investigation_starter,
    resolve_datasource_id,
)
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing.models.issue import IssueStatus
from dataing.services.investigation import (
    DatasetRequiredError,
    InvestigationStarterService,
    InvestigationStartFailed,
    IssueNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/issues", tags=["issues"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
InvestigationStarterDep = Annotated[InvestigationStarterService, Depends(get_investigation_starter)]


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

# Lifecycle order, used to list allowed transitions deterministically.
_STATUS_ORDER = [status.value for status in IssueStatus]

_OWNED_STATUSES = frozenset({IssueStatus.IN_PROGRESS.value, IssueStatus.BLOCKED.value})


def missing_transition_fields(
    new_status: str,
    assignee_user_id: UUID | None,
    acknowledged_by: UUID | None,
    resolution_note: str | None,
    has_linked_investigation: bool = False,
) -> list[str]:
    """Return the fields a move to new_status still needs, given the issue's values.

    In progress and blocked need an owner (assignee_user_id or acknowledged_by);
    resolved needs a resolution_note unless a linked investigation has a synthesis.
    """
    if new_status in _OWNED_STATUSES and not assignee_user_id and not acknowledged_by:
        return ["assignee_user_id"]
    if (
        new_status == IssueStatus.RESOLVED.value
        and not resolution_note
        and not has_linked_investigation
    ):
        return ["resolution_note"]
    return []


def transition_options(
    current_status: str,
    assignee_user_id: UUID | None,
    acknowledged_by: UUID | None,
    resolution_note: str | None,
    has_linked_investigation: bool,
) -> tuple[list[str], dict[str, list[str]]]:
    """Return the allowed moves from current_status and what each still needs.

    Returns:
        Tuple of (allowed_transitions, transition_requirements). The allowed
        transitions are the state machine's moves in lifecycle order. The
        requirements map only the moves whose guard the issue does not already
        satisfy to the fields the client must send in the same PATCH.
    """
    targets = STATE_TRANSITIONS.get(current_status, set())
    allowed = [status for status in _STATUS_ORDER if status in targets]
    requirements: dict[str, list[str]] = {}
    for target in allowed:
        missing = missing_transition_fields(
            target, assignee_user_id, acknowledged_by, resolution_note, has_linked_investigation
        )
        if missing:
            requirements[target] = missing
    return allowed, requirements


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
    valid_transitions = STATE_TRANSITIONS.get(current_status, set())
    if new_status not in valid_transitions:
        return False, f"Cannot transition from {current_status} to {new_status}"

    missing = missing_transition_fields(
        new_status, assignee_user_id, acknowledged_by, resolution_note, has_linked_investigation
    )
    if missing == ["assignee_user_id"]:
        return False, f"Transition to {new_status} requires an assignee or acknowledged_by user"
    if missing == ["resolution_note"]:
        return False, "Transition to RESOLVED requires resolution_note or a linked investigation"

    return True, ""


# ============================================================================
# Pydantic Schemas
# ============================================================================

# Issue context is a small hint (e.g. observed_at, column), not a payload store.
MAX_CONTEXT_BYTES = 4096


def _check_context_size(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Reject a context whose JSON encoding exceeds MAX_CONTEXT_BYTES."""
    if value is not None and len(to_json_string(value).encode()) > MAX_CONTEXT_BYTES:
        raise ValueError(f"context must be at most {MAX_CONTEXT_BYTES} bytes as JSON")
    return value


class IssueCreate(BaseModel):
    """Request body for creating an issue."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: str | None = Field(None, pattern="^P[0-3]$")
    severity: str | None = Field(None, pattern="^(low|medium|high|critical)$")
    dataset_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Where the problem was seen, e.g. observed_at and column",
    )

    check_context_size = field_validator("context")(_check_context_size)


# Fields that may not be cleared with an explicit null.
_NON_NULLABLE_UPDATE_FIELDS = ("title", "status")


class IssueUpdate(BaseModel):
    """Request body for updating an issue.

    A field sent as null clears the column; a field left out is unchanged.
    Title and status cannot be null. A null context resets it to an empty object,
    and null labels remove every label.
    """

    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    status: str | None = Field(None, pattern="^(open|triaged|in_progress|blocked|resolved|closed)$")
    priority: str | None = Field(None, pattern="^P[0-3]$")
    severity: str | None = Field(None, pattern="^(low|medium|high|critical)$")
    assignee_user_id: UUID | None = None
    acknowledged_by: UUID | None = None
    resolution_note: str | None = None
    dataset_id: str | None = None
    due_at: datetime | None = None
    context: dict[str, Any] | None = None
    labels: list[str] | None = None

    check_context_size = field_validator("context")(_check_context_size)

    @model_validator(mode="after")
    def reject_required_nulls(self) -> IssueUpdate:
        """Refuse explicit nulls for fields the issue must always have."""
        for name in _NON_NULLABLE_UPDATE_FIELDS:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


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
    due_at: datetime | None
    assignee_user_id: UUID | None
    acknowledged_by: UUID | None
    created_by_user_id: UUID | None
    author_type: str
    source_provider: str | None
    source_external_id: str | None
    source_external_url: str | None
    resolution_note: str | None
    context: dict[str, Any]
    labels: list[str]
    allowed_transitions: list[str] = Field(
        description="Statuses this issue may move to (the state machine's moves)"
    )
    transition_requirements: dict[str, list[str]] = Field(
        description=(
            "For allowed moves whose guard the issue does not yet satisfy, the fields "
            "to send in the same PATCH (assignee_user_id or resolution_note)"
        )
    )
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


def _decode_json_object(value: Any) -> dict[str, Any]:
    """Decode a JSONB column value (text without a codec) into a dict."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


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


def _needs_synthesis_check(row: dict[str, Any]) -> bool:
    """Whether the resolve guard for this issue depends on a linked synthesis."""
    return (
        IssueStatus.RESOLVED.value in STATE_TRANSITIONS.get(row["status"], set())
        and not (row["resolution_note"])
    )


async def _issues_with_synthesis(db: AppDatabase, rows: list[dict[str, Any]]) -> set[UUID]:
    """Return the ids among rows that have a linked investigation with a synthesis.

    Only rows whose resolve guard depends on it are looked up, in one query.
    """
    ids = [row["id"] for row in rows if _needs_synthesis_check(row)]
    if not ids:
        return set()
    found = await db.fetch_all(
        """
        SELECT DISTINCT issue_id FROM issue_investigation_runs
        WHERE issue_id = ANY($1::uuid[]) AND synthesis_summary IS NOT NULL
        """,
        ids,
    )
    return {r["issue_id"] for r in found}


def _build_issue_response(
    row: dict[str, Any], labels: list[str], has_linked_investigation: bool
) -> IssueResponse:
    """Build an IssueResponse from an issues row selected with ISSUE_COLUMNS."""
    allowed, requirements = transition_options(
        row["status"],
        row["assignee_user_id"],
        row["acknowledged_by"],
        row["resolution_note"],
        has_linked_investigation,
    )
    return IssueResponse(
        id=row["id"],
        number=row["number"],
        title=row["title"],
        description=row["description"],
        status=row["status"],
        priority=row["priority"],
        severity=row["severity"],
        dataset_id=row["dataset_id"],
        due_at=row["due_at"],
        assignee_user_id=row["assignee_user_id"],
        acknowledged_by=row["acknowledged_by"],
        created_by_user_id=row["created_by_user_id"],
        author_type=row["author_type"],
        source_provider=row["source_provider"],
        source_external_id=row["source_external_id"],
        source_external_url=row["source_external_url"],
        resolution_note=row["resolution_note"],
        context=_decode_json_object(row["context"]),
        labels=labels,
        allowed_transitions=allowed,
        transition_requirements=requirements,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        closed_at=row["closed_at"],
    )


async def _issue_response(db: AppDatabase, row: dict[str, Any]) -> IssueResponse:
    """Load labels and the synthesis flag for one issue row and build its response."""
    labels = await _get_issue_labels(db, row["id"])
    synthesized = await _issues_with_synthesis(db, [row])
    return _build_issue_response(row, labels, row["id"] in synthesized)


async def _record_confirmed_cause(
    db: AppDatabase, issue_id: UUID, actor_user_id: UUID | None
) -> None:
    """Record the confirmed root cause an issue was resolved with, if it has one."""
    confirmed = await db.fetch_one(
        """
        SELECT investigation_id, synthesis_summary FROM issue_investigation_runs
        WHERE issue_id = $1 AND outcome_verdict = 'confirmed'
        ORDER BY outcome_reviewed_at DESC LIMIT 1
        """,
        issue_id,
    )
    if confirmed is None:
        return
    await record_issue_event(
        db,
        issue_id,
        "resolved_with_cause",
        actor_user_id,
        {
            "investigation_id": str(confirmed["investigation_id"]),
            "root_cause": confirmed["synthesis_summary"],
        },
    )


# PATCHable columns, in the order they are written.
_UPDATABLE_COLUMNS = (
    "title",
    "description",
    "status",
    "priority",
    "severity",
    "assignee_user_id",
    "acknowledged_by",
    "resolution_note",
    "dataset_id",
    "due_at",
    "context",
)


def _field_change_event(field: str, old: Any, new: Any) -> tuple[str, dict[str, Any]]:
    """Return the (event_type, payload) recorded for a changed issue field."""
    before, after = to_json_safe(old), to_json_safe(new)
    if field == "status":
        return "status_changed", {"from": before, "to": after}
    if field == "assignee_user_id":
        return "assigned", {"assignee_user_id": after, "from": before, "to": after}
    if field == "acknowledged_by":
        return "acknowledged", {"acknowledged_by": after, "from": before, "to": after}
    if field in ("priority", "severity"):
        return f"{field}_changed", {"from": before, "to": after}
    return "field_changed", {"field": field, "from": before, "to": after}


def _changed_fields(current: dict[str, Any], body: IssueUpdate) -> dict[str, Any]:
    """Return the columns the PATCH body sets to a value different from current.

    Only fields present in the request body count; an explicit null clears the
    column, except context, which resets to an empty object.
    """
    changes: dict[str, Any] = {}
    for field in _UPDATABLE_COLUMNS:
        if field not in body.model_fields_set:
            continue
        new = getattr(body, field)
        old = current[field]
        if field == "context":
            new = new or {}
            old = _decode_json_object(old)
        if new != old:
            changes[field] = new
    return changes


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
        SELECT {ISSUE_COLUMNS}
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

    synthesized = await _issues_with_synthesis(db, rows)
    items = []
    for row in rows:
        labels = await _get_issue_labels(db, row["id"])
        items.append(_build_issue_response(row, labels, row["id"] in synthesized))

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
    auth: WriteScopeDep,
    db: AppDbDep,
    body: IssueCreate,
) -> IssueResponse:
    """Create a new issue.

    Issues are created in OPEN status. Number is auto-assigned per-tenant.
    """
    row = await open_issue(
        db,
        tenant_id=auth.tenant_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        severity=body.severity,
        dataset_id=body.dataset_id,
        labels=body.labels,
        context=body.context,
        created_by=auth.user_id,
    )
    return await _issue_response(db, row)


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
        f"SELECT {ISSUE_COLUMNS} FROM issues WHERE id = $1 AND tenant_id = $2",
        issue_id,
        auth.tenant_id,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")

    return await _issue_response(db, row)


@router.patch("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: UUID,
    auth: WriteScopeDep,
    db: AppDbDep,
    body: IssueUpdate,
) -> IssueResponse:
    """Update issue fields.

    A field sent as null clears it; a field left out is unchanged. A status
    change is validated against the issue as it will be after this PATCH, so
    status and assignee (or resolution_note) can be sent together. Every
    changed field is recorded as an issue event.
    """
    current = await db.fetch_one(
        f"SELECT {ISSUE_COLUMNS} FROM issues WHERE id = $1 AND tenant_id = $2",
        issue_id,
        auth.tenant_id,
    )

    if not current:
        raise HTTPException(status_code=404, detail="Issue not found")

    changes = _changed_fields(current, body)

    if "status" in changes:
        effective = {**current, **changes}
        has_investigation = await _has_linked_investigation(db, issue_id)
        is_valid, error = validate_state_transition(
            current["status"],
            changes["status"],
            effective["assignee_user_id"],
            effective["acknowledged_by"],
            effective["resolution_note"],
            has_investigation,
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=error)

    old_labels = await _get_issue_labels(db, issue_id)
    labels_changed = "labels" in body.model_fields_set and sorted(set(body.labels or [])) != sorted(
        old_labels
    )

    row = current
    if changes or labels_changed:
        updates: list[str] = []
        params: list[Any] = []
        for field, value in changes.items():
            params.append(to_json_string(value) if field == "context" else value)
            updates.append(f"{field} = ${len(params)}")

        if "status" in changes:
            if changes["status"] == IssueStatus.CLOSED.value:
                params.append(datetime.now(UTC))
                updates.append(f"closed_at = ${len(params)}")
            elif current["status"] == IssueStatus.CLOSED.value:
                updates.append("closed_at = NULL")

        params.append(datetime.now(UTC))
        updates.append(f"updated_at = ${len(params)}")
        params.extend([issue_id, auth.tenant_id])

        updated = await db.execute_returning(
            f"""
            UPDATE issues
            SET {", ".join(updates)}
            WHERE id = ${len(params) - 1} AND tenant_id = ${len(params)}
            RETURNING {ISSUE_COLUMNS}
            """,
            *params,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Issue not found")
        row = updated

        for field, value in changes.items():
            old = _decode_json_object(current[field]) if field == "context" else current[field]
            event_type, payload = _field_change_event(field, old, value)
            await record_issue_event(db, issue_id, event_type, auth.user_id, payload)

        if changes.get("status") == IssueStatus.RESOLVED.value:
            await _record_confirmed_cause(db, issue_id, auth.user_id)

    if labels_changed:
        new_labels = sorted(set(body.labels or []))
        await _set_issue_labels(db, issue_id, new_labels)
        for label in sorted(set(new_labels) - set(old_labels)):
            await record_issue_event(db, issue_id, "label_added", auth.user_id, {"label": label})
        for label in sorted(set(old_labels) - set(new_labels)):
            await record_issue_event(db, issue_id, "label_removed", auth.user_id, {"label": label})

    return await _issue_response(db, row)


# ============================================================================
# Comment Schemas
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
    """Request body for starting an investigation from an issue with a brief."""

    brief: InvestigationBrief
    dataset_id: str | None = None  # Inherits from issue if not provided
    datasource_id: UUID | None = None  # Brief scope, then tenant default, if not provided
    execution_profile: str = Field(
        default="standard",
        pattern="^(safe|standard|deep)$",
    )
    source_thread_id: UUID | None = None  # The thread the brief was drafted in
    parent_run_id: UUID | None = None  # Set for "Continue investigating"


class InvestigationRunResponse(BaseModel):
    """Response for an investigation run."""

    id: UUID
    issue_id: UUID
    investigation_id: UUID
    trigger_type: str
    brief: dict[str, Any]
    source_thread_id: UUID | None
    parent_run_id: UUID | None
    execution_profile: str
    approval_status: str | None
    confidence: float | None
    root_cause_tag: str | None
    synthesis_summary: str | None
    created_at: datetime
    completed_at: datetime | None
    outcome_verdict: str | None = None  # confirmed | rejected, once someone reviewed it
    outcome_note: str | None = None
    outcome_reviewed_by: UUID | None = None
    outcome_reviewed_at: datetime | None = None
    number: int  # The run's position among the issue's runs, by start time
    status: str  # running, completed or failed, from the investigation's outcome
    error: str | None = None  # Why a failed run failed


def _run_response(row: dict[str, Any]) -> InvestigationRunResponse:
    """Convert an issue_investigation_runs row (brief as JSON text) to its API shape."""
    brief = row["brief"]
    return InvestigationRunResponse(
        **{
            **{field: row.get(field) for field in InvestigationRunResponse.model_fields},
            "brief": json.loads(brief) if isinstance(brief, str) else brief,
        }
    )


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

    items = [_run_response(row) for row in await list_runs(db, issue_id)]

    return InvestigationRunListResponse(items=items, total=len(items))


@router.post(
    "/{issue_id}/investigation-runs",
    response_model=InvestigationRunResponse,
    status_code=201,
)
async def spawn_investigation(
    issue_id: UUID,
    http_request: Request,
    auth: WriteScopeDep,
    db: AppDbDep,
    investigation_starter: InvestigationStarterDep,
    body: InvestigationRunCreate,
) -> InvestigationRunResponse:
    """Start an investigation from an issue with an editable brief.

    The manager and its subagents start from the brief: its symptom is what they
    investigate, its findings are facts, its exclusions are not proposed again and
    its leads are tested first. The brief's scope tables join the issue's dataset
    as reference tables. The run appears in the issue's shared thread.

    Requires user identity (JWT auth or user-scoped API key).
    """
    if auth.user_id is None:
        raise HTTPException(
            status_code=403,
            detail="User identity required to spawn investigations",
        )
    await _verify_issue_access(db, issue_id, auth.tenant_id)

    brief = body.brief
    if body.parent_run_id is not None:
        parent = await db.fetch_one(
            "SELECT id FROM issue_investigation_runs WHERE id = $1 AND issue_id = $2",
            body.parent_run_id,
            issue_id,
        )
        if parent is None:
            raise HTTPException(status_code=400, detail="parent_run_id is not a run of this issue")

    try:
        datasource_id = await resolve_datasource_id(
            http_request,
            auth.tenant_id,
            explicit_id=body.datasource_id or brief.scope.datasource_id,
        )
    except ValueError as e:
        error_msg = str(e)
        if error_msg.startswith("ambiguous_datasource:"):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "ambiguous_datasource",
                    "message": "Multiple datasources match. Please specify which to use.",
                    "hint": "Specify datasource_id in the request body.",
                },
            ) from e
        raise HTTPException(status_code=400, detail=error_msg) from e

    try:
        started = await investigation_starter.start(
            tenant_id=auth.tenant_id,
            datasource_id=datasource_id,
            trigger_type="human",
            brief=brief,
            issue_id=issue_id,
            dataset_id=body.dataset_id,
            actor_user_id=auth.user_id,
            trigger_ref={"user_id": str(auth.user_id)},
            execution_profile=body.execution_profile,
            source_thread_id=body.source_thread_id,
            parent_run_id=body.parent_run_id,
        )
    except IssueNotFoundError as e:
        raise HTTPException(status_code=404, detail="Issue not found") from e
    except DatasetRequiredError as e:
        raise HTTPException(
            status_code=400,
            detail="dataset_id required - not set on issue, request or brief scope",
        ) from e
    except (InvestigationStartFailed, RuntimeError) as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return _run_response(started.run)


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
            payload=_decode_json_object(row["payload"]),
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
                            "payload": _decode_json_object(row["payload"]),
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
