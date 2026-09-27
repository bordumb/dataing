"""API routes for runbooks and knowledge base (EE)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    require_scope,
    verify_api_key,
)
from dataing_ee.core.runbook.generator import RunbookGenerator
from dataing_ee.core.runbook.similarity import SimilarityScorer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runbooks", tags=["runbooks"])

# Dependencies
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


# ============================================================================
# Request/Response Schemas
# ============================================================================


class RunbookCreate(BaseModel):
    """Request to create a runbook."""

    title: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)
    summary: str | None = None
    dataset_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    symptoms: list[dict[str, Any]] = Field(default_factory=list)
    root_cause: str | None = None
    verification_steps: list[dict[str, Any]] = Field(default_factory=list)
    fix_steps: list[dict[str, Any]] = Field(default_factory=list)
    prevention_notes: str | None = None
    is_published: bool = False


class RunbookUpdate(BaseModel):
    """Request to update a runbook."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    summary: str | None = None
    dataset_id: str | None = None
    labels: list[str] | None = None
    symptoms: list[dict[str, Any]] | None = None
    root_cause: str | None = None
    verification_steps: list[dict[str, Any]] | None = None
    fix_steps: list[dict[str, Any]] | None = None
    prevention_notes: str | None = None
    is_published: bool | None = None


class RunbookResponse(BaseModel):
    """Runbook response."""

    id: UUID
    tenant_id: UUID
    title: str
    body: str
    summary: str | None
    dataset_id: str | None
    labels: list[str]
    symptoms: list[dict[str, Any]]
    root_cause: str | None
    verification_steps: list[dict[str, Any]]
    fix_steps: list[dict[str, Any]]
    prevention_notes: str | None
    is_published: bool
    view_count: int
    usefulness_score: float
    created_from_issue_id: UUID | None
    created_from_investigation_id: UUID | None
    created_at: datetime
    updated_at: datetime


class RunbookListItem(BaseModel):
    """Runbook list item (minimal fields)."""

    id: UUID
    title: str
    summary: str | None
    dataset_id: str | None
    labels: list[str]
    is_published: bool
    view_count: int
    created_at: datetime


class RunbookListResponse(BaseModel):
    """List of runbooks response."""

    items: list[RunbookListItem]
    total: int


class SuggestedRunbook(BaseModel):
    """Suggested runbook with similarity score."""

    id: UUID
    title: str
    summary: str | None
    score: float
    matched_terms: list[str]


class SuggestedRunbooksResponse(BaseModel):
    """Suggested runbooks response."""

    items: list[SuggestedRunbook]


class GenerateRunbookRequest(BaseModel):
    """Request to generate a runbook from an issue."""

    publish: bool = False


class LinkFeedbackRequest(BaseModel):
    """Request to provide feedback on a runbook link."""

    was_helpful: bool
    feedback_notes: str | None = None


# ============================================================================
# Routes
# ============================================================================


@router.get("", response_model=RunbookListResponse)
async def list_runbooks(
    auth: AuthDep,
    db: AppDbDep,
    published_only: bool = Query(default=False),
    dataset_id: str | None = Query(default=None),
    label: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RunbookListResponse:
    """List runbooks for the tenant."""
    # Build query
    conditions = ["tenant_id = $1"]
    params: list[Any] = [auth.tenant_id]
    param_idx = 2

    if published_only:
        conditions.append("is_published = true")

    if dataset_id:
        conditions.append(f"dataset_id = ${param_idx}")
        params.append(dataset_id)
        param_idx += 1

    if label:
        conditions.append(f"${param_idx} = ANY(labels)")
        params.append(label)
        param_idx += 1

    if search:
        conditions.append(f"search_vector @@ plainto_tsquery('english', ${param_idx})")
        params.append(search)
        param_idx += 1

    where_clause = " AND ".join(conditions)

    # Get total count
    count_row = await db.fetch_one(
        f"SELECT COUNT(*) as count FROM runbooks WHERE {where_clause}",
        *params,
    )
    total = count_row["count"] if count_row else 0

    # Get items
    params.extend([limit, offset])
    rows = await db.fetch_all(
        f"""
        SELECT id, title, summary, dataset_id, labels, is_published, view_count, created_at
        FROM runbooks
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """,
        *params,
    )

    items = [
        RunbookListItem(
            id=row["id"],
            title=row["title"],
            summary=row.get("summary"),
            dataset_id=row.get("dataset_id"),
            labels=row.get("labels") or [],
            is_published=row["is_published"],
            view_count=row["view_count"],
            created_at=row["created_at"],
        )
        for row in rows
    ]

    return RunbookListResponse(items=items, total=total)


@router.post("", response_model=RunbookResponse, status_code=status.HTTP_201_CREATED)
async def create_runbook(
    auth: WriteScopeDep,
    db: AppDbDep,
    body: RunbookCreate,
) -> RunbookResponse:
    """Create a new runbook."""
    row = await db.fetch_one(
        """
        INSERT INTO runbooks (
            tenant_id, title, body, summary, dataset_id, labels,
            symptoms, root_cause, verification_steps, fix_steps,
            prevention_notes, is_published, created_by
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        RETURNING *
        """,
        auth.tenant_id,
        body.title,
        body.body,
        body.summary,
        body.dataset_id,
        body.labels,
        to_json_string(body.symptoms),
        body.root_cause,
        to_json_string(body.verification_steps),
        to_json_string(body.fix_steps),
        body.prevention_notes,
        body.is_published,
        auth.user_id,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create runbook",
        )

    logger.info(f"runbook_created: {row['id']} title={body.title}")

    return _row_to_response(row)


@router.get("/{runbook_id}", response_model=RunbookResponse)
async def get_runbook(
    auth: AuthDep,
    db: AppDbDep,
    runbook_id: UUID,
    increment_view: bool = Query(default=True),
) -> RunbookResponse:
    """Get a runbook by ID."""
    row = await db.fetch_one(
        "SELECT * FROM runbooks WHERE id = $1 AND tenant_id = $2",
        runbook_id,
        auth.tenant_id,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Runbook not found",
        )

    # Increment view count
    if increment_view:
        await db.execute(
            "UPDATE runbooks SET view_count = view_count + 1 WHERE id = $1",
            runbook_id,
        )

    return _row_to_response(row)


@router.patch("/{runbook_id}", response_model=RunbookResponse)
async def update_runbook(
    auth: WriteScopeDep,
    db: AppDbDep,
    runbook_id: UUID,
    body: RunbookUpdate,
) -> RunbookResponse:
    """Update a runbook."""
    # Check exists
    existing = await db.fetch_one(
        "SELECT id FROM runbooks WHERE id = $1 AND tenant_id = $2",
        runbook_id,
        auth.tenant_id,
    )

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Runbook not found",
        )

    # Build update
    updates: list[str] = []
    params: list[Any] = []
    param_idx = 1

    if body.title is not None:
        updates.append(f"title = ${param_idx}")
        params.append(body.title)
        param_idx += 1

    if body.body is not None:
        updates.append(f"body = ${param_idx}")
        params.append(body.body)
        param_idx += 1

    if body.summary is not None:
        updates.append(f"summary = ${param_idx}")
        params.append(body.summary)
        param_idx += 1

    if body.dataset_id is not None:
        updates.append(f"dataset_id = ${param_idx}")
        params.append(body.dataset_id)
        param_idx += 1

    if body.labels is not None:
        updates.append(f"labels = ${param_idx}")
        params.append(body.labels)
        param_idx += 1

    if body.symptoms is not None:
        updates.append(f"symptoms = ${param_idx}")
        params.append(to_json_string(body.symptoms))
        param_idx += 1

    if body.root_cause is not None:
        updates.append(f"root_cause = ${param_idx}")
        params.append(body.root_cause)
        param_idx += 1

    if body.verification_steps is not None:
        updates.append(f"verification_steps = ${param_idx}")
        params.append(to_json_string(body.verification_steps))
        param_idx += 1

    if body.fix_steps is not None:
        updates.append(f"fix_steps = ${param_idx}")
        params.append(to_json_string(body.fix_steps))
        param_idx += 1

    if body.prevention_notes is not None:
        updates.append(f"prevention_notes = ${param_idx}")
        params.append(body.prevention_notes)
        param_idx += 1

    if body.is_published is not None:
        updates.append(f"is_published = ${param_idx}")
        params.append(body.is_published)
        param_idx += 1

    if not updates:
        # No updates, return existing
        row = await db.fetch_one(
            "SELECT * FROM runbooks WHERE id = $1",
            runbook_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Runbook not found")
        return _row_to_response(row)

    # Add updated_by
    updates.append(f"updated_by = ${param_idx}")
    params.append(auth.user_id)
    param_idx += 1

    # Add WHERE clause params
    params.append(runbook_id)

    row = await db.fetch_one(
        f"""
        UPDATE runbooks
        SET {", ".join(updates)}
        WHERE id = ${param_idx}
        RETURNING *
        """,
        *params,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update runbook",
        )

    logger.info(f"runbook_updated: {runbook_id}")

    return _row_to_response(row)


@router.delete("/{runbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_runbook(
    auth: AdminScopeDep,
    db: AppDbDep,
    runbook_id: UUID,
) -> None:
    """Delete a runbook (admin only)."""
    result = await db.execute(
        "DELETE FROM runbooks WHERE id = $1 AND tenant_id = $2",
        runbook_id,
        auth.tenant_id,
    )

    if result == "DELETE 0":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Runbook not found",
        )

    logger.info(f"runbook_deleted: {runbook_id}")


# ============================================================================
# Issue-Related Routes
# ============================================================================


@router.post(
    "/from-issue/{issue_id}",
    response_model=RunbookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_runbook_from_issue(
    auth: WriteScopeDep,
    db: AppDbDep,
    issue_id: UUID,
    body: GenerateRunbookRequest,
) -> RunbookResponse:
    """Generate a runbook from a resolved issue and its investigation."""
    # Check issue exists and belongs to tenant
    issue = await db.fetch_one(
        "SELECT id, status FROM issues WHERE id = $1 AND tenant_id = $2",
        issue_id,
        auth.tenant_id,
    )

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found",
        )

    # Check if runbook already exists for this issue
    existing = await db.fetch_one(
        "SELECT id FROM runbooks WHERE created_from_issue_id = $1",
        issue_id,
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Runbook already exists for this issue",
        )

    # Generate runbook
    generator = RunbookGenerator()
    generated = await generator.generate_from_issue(db, auth.tenant_id, issue_id)

    if not generated:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not generate runbook from issue",
        )

    # Insert runbook
    row = await db.fetch_one(
        """
        INSERT INTO runbooks (
            tenant_id, title, body, summary, dataset_id, labels,
            symptoms, root_cause, verification_steps, fix_steps,
            prevention_notes, is_published,
            created_from_issue_id, created_from_investigation_id,
            created_by
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        RETURNING *
        """,
        auth.tenant_id,
        generated.title,
        generated.body,
        generated.summary,
        generated.dataset_id,
        generated.labels,
        to_json_string(generated.symptoms),
        generated.root_cause,
        to_json_string(generated.verification_steps),
        to_json_string(generated.fix_steps),
        generated.prevention_notes,
        body.publish,
        issue_id,
        generated.investigation_id,
        auth.user_id,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create runbook",
        )

    logger.info(f"runbook_generated: {row['id']} from_issue={issue_id}")

    return _row_to_response(row)


@router.get("/suggested/{issue_id}", response_model=SuggestedRunbooksResponse)
async def get_suggested_runbooks(
    auth: AuthDep,
    db: AppDbDep,
    issue_id: UUID,
    limit: int = Query(default=5, ge=1, le=20),
    min_score: float = Query(default=0.1, ge=0.0, le=1.0),
) -> SuggestedRunbooksResponse:
    """Get runbooks suggested for an issue based on similarity."""
    # Check issue exists
    issue = await db.fetch_one(
        "SELECT id FROM issues WHERE id = $1 AND tenant_id = $2",
        issue_id,
        auth.tenant_id,
    )

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found",
        )

    # Find similar runbooks
    scorer = SimilarityScorer()
    similar = await scorer.find_similar_runbooks(
        db=db,
        tenant_id=auth.tenant_id,
        issue_id=issue_id,
        limit=limit,
        min_score=min_score,
    )

    items = [
        SuggestedRunbook(
            id=r.runbook_id,
            title=r.title,
            summary=r.summary,
            score=r.score,
            matched_terms=r.matched_terms,
        )
        for r in similar
    ]

    return SuggestedRunbooksResponse(items=items)


@router.post(
    "/{runbook_id}/link/{issue_id}",
    status_code=status.HTTP_201_CREATED,
)
async def link_runbook_to_issue(
    auth: WriteScopeDep,
    db: AppDbDep,
    runbook_id: UUID,
    issue_id: UUID,
    link_type: str = Query(default="referenced"),
) -> dict[str, str]:
    """Link a runbook to an issue."""
    # Verify runbook exists
    runbook = await db.fetch_one(
        "SELECT id FROM runbooks WHERE id = $1 AND tenant_id = $2",
        runbook_id,
        auth.tenant_id,
    )

    if not runbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Runbook not found",
        )

    # Verify issue exists
    issue = await db.fetch_one(
        "SELECT id FROM issues WHERE id = $1 AND tenant_id = $2",
        issue_id,
        auth.tenant_id,
    )

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found",
        )

    # Calculate similarity score
    scorer = SimilarityScorer()
    score = await scorer.score_runbook_for_issue(
        db=db,
        tenant_id=auth.tenant_id,
        issue_id=issue_id,
        runbook_id=runbook_id,
    )

    # Create link (upsert)
    await db.execute(
        """
        INSERT INTO runbook_links (runbook_id, issue_id, score, link_type, created_by)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (runbook_id, issue_id)
        DO UPDATE SET link_type = $4, score = $3
        """,
        runbook_id,
        issue_id,
        score,
        link_type,
        auth.user_id,
    )

    logger.info(f"runbook_linked: runbook={runbook_id} issue={issue_id}")

    return {"status": "linked"}


@router.post("/{runbook_id}/link/{issue_id}/feedback")
async def provide_link_feedback(
    auth: AuthDep,
    db: AppDbDep,
    runbook_id: UUID,
    issue_id: UUID,
    body: LinkFeedbackRequest,
) -> dict[str, str]:
    """Provide feedback on a runbook link."""
    async with db.acquire() as conn, conn.transaction():
        # runbook_links has no tenant_id, so this tenant-scoped lookup is what
        # keeps the writes below inside the caller's tenant. Locking the row
        # serializes concurrent feedback on the runbook, so the recount below
        # sees every verdict committed before it.
        runbook = await conn.fetchrow(
            "SELECT id FROM runbooks WHERE id = $1 AND tenant_id = $2 FOR UPDATE",
            runbook_id,
            auth.tenant_id,
        )

        if not runbook:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Runbook not found",
            )

        result = await conn.execute(
            """
            UPDATE runbook_links
            SET was_helpful = $1, feedback_notes = $2
            WHERE runbook_id = $3 AND issue_id = $4
            """,
            body.was_helpful,
            body.feedback_notes,
            runbook_id,
            issue_id,
        )

        if result == "UPDATE 0":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Link not found",
            )

        # Derive the score from every link's current verdict instead of nudging
        # it per request: re-posting a verdict leaves it unchanged, and flipping
        # one moves it exactly once.
        counts = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE was_helpful) AS helpful,
                COUNT(*) FILTER (WHERE NOT was_helpful) AS not_helpful
            FROM runbook_links
            WHERE runbook_id = $1
            """,
            runbook_id,
        )
        await conn.execute(
            "UPDATE runbooks SET usefulness_score = $1 WHERE id = $2",
            _usefulness_score(counts["helpful"], counts["not_helpful"]),
            runbook_id,
        )

    return {"status": "feedback_recorded"}


# ============================================================================
# Helpers
# ============================================================================


def _usefulness_score(helpful: int, not_helpful: int) -> float:
    """Score a runbook from its links' verdicts: +0.1 per helpful, -0.05 per not, floor 0."""
    return max(0.0, 0.1 * helpful - 0.05 * not_helpful)


def _json_list(value: Any) -> list[dict[str, Any]]:
    """A JSONB array column value as a list (AppDatabase returns JSONB as text)."""
    if isinstance(value, str):
        value = json.loads(value)
    result: list[dict[str, Any]] = value or []
    return result


def _row_to_response(row: dict[str, Any]) -> RunbookResponse:
    """Convert database row to response model."""
    return RunbookResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        title=row["title"],
        body=row["body"],
        summary=row.get("summary"),
        dataset_id=row.get("dataset_id"),
        labels=row.get("labels") or [],
        symptoms=_json_list(row.get("symptoms")),
        root_cause=row.get("root_cause"),
        verification_steps=_json_list(row.get("verification_steps")),
        fix_steps=_json_list(row.get("fix_steps")),
        prevention_notes=row.get("prevention_notes"),
        is_published=row["is_published"],
        view_count=row["view_count"],
        usefulness_score=row["usefulness_score"],
        created_from_issue_id=row.get("created_from_issue_id"),
        created_from_investigation_id=row.get("created_from_investigation_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
