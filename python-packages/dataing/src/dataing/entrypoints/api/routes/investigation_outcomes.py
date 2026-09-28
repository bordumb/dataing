"""Reviewing an investigation's outcome (spec 0001 §7.10).

A person confirms or rejects the root cause a finished run reached. The verdict
is stored on the issue's run, sent to the feedback log, and shown in the thread.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.investigation_feedback import EventType, InvestigationFeedbackAdapter
from dataing.entrypoints.api.deps import get_app_db, get_feedback_adapter
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope
from dataing.entrypoints.api.routes.issues import (
    RUN_COLUMNS,
    InvestigationRunResponse,
    _record_issue_event,
    _run_response,
)

router = APIRouter(prefix="/investigations", tags=["investigations"])

WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
FeedbackDep = Annotated[InvestigationFeedbackAdapter, Depends(get_feedback_adapter)]


class OutcomeReview(BaseModel):
    """A verdict on a finished investigation's root cause."""

    verdict: Literal["confirmed", "rejected"]
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _rejection_needs_a_reason(self) -> OutcomeReview:
        if self.verdict == "rejected" and not (self.note or "").strip():
            raise ValueError("Rejecting an outcome needs a note saying why")
        return self


@router.post("/{investigation_id}/outcome-review", response_model=InvestigationRunResponse)
async def review_outcome(
    investigation_id: UUID,
    body: OutcomeReview,
    auth: WriteScopeDep,
    db: AppDbDep,
    feedback: FeedbackDep,
) -> InvestigationRunResponse:
    """Confirm or reject the root cause an issue's investigation reached."""
    run = await db.fetch_one(
        """
        SELECT r.id, r.issue_id, inv.outcome
        FROM issue_investigation_runs r
        JOIN issues i ON i.id = r.issue_id
        JOIN investigations inv ON inv.id = r.investigation_id
        WHERE r.investigation_id = $1 AND i.tenant_id = $2
        """,
        investigation_id,
        auth.tenant_id,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Investigation run not found")
    if run["outcome"] is None:
        raise HTTPException(status_code=409, detail="The investigation has no outcome yet")

    updated = await db.execute_returning(
        f"""
        UPDATE issue_investigation_runs
        SET outcome_verdict = $2, outcome_note = $3,
            outcome_reviewed_by = $4, outcome_reviewed_at = NOW()
        WHERE id = $1
        RETURNING {RUN_COLUMNS}
        """,
        run["id"],
        body.verdict,
        body.note,
        auth.user_id,
    )
    assert updated is not None

    await feedback.emit(
        tenant_id=auth.tenant_id,
        event_type=EventType.FEEDBACK_SYNTHESIS,
        event_data={
            "target_id": str(investigation_id),
            "rating": 1 if body.verdict == "confirmed" else -1,
            "reason": body.verdict,
            "comment": body.note,
        },
        investigation_id=investigation_id,
        actor_id=auth.user_id,
        actor_type="user",
    )
    await _record_issue_event(
        db,
        run["issue_id"],
        "outcome_reviewed",
        auth.user_id,
        {
            "investigation_id": str(investigation_id),
            "verdict": body.verdict,
            "note": body.note,
        },
    )
    return _run_response(updated)
