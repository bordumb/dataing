"""API routes for user feedback collection."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dataing.adapters.audit import audited
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.investigation_feedback import EventType, InvestigationFeedbackAdapter
from dataing.entrypoints.api.deps import get_app_db, get_feedback_adapter
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/investigation-feedback", tags=["investigation-feedback"])

AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
InvestigationFeedbackAdapterDep = Annotated[
    InvestigationFeedbackAdapter, Depends(get_feedback_adapter)
]
DbDep = Annotated[AppDatabase, Depends(get_app_db)]


class FeedbackCreate(BaseModel):
    """Request body for submitting feedback."""

    target_type: Literal["hypothesis", "query", "evidence", "synthesis", "investigation"]
    target_id: UUID
    investigation_id: UUID
    rating: Literal[1, -1]
    reason: str | None = None
    comment: str | None = None


class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""

    id: UUID
    created_at: datetime


# Map target_type to EventType
TARGET_TYPE_TO_EVENT = {
    "hypothesis": EventType.FEEDBACK_HYPOTHESIS,
    "query": EventType.FEEDBACK_QUERY,
    "evidence": EventType.FEEDBACK_EVIDENCE,
    "synthesis": EventType.FEEDBACK_SYNTHESIS,
    "investigation": EventType.FEEDBACK_INVESTIGATION,
}


@router.post("/", status_code=201, response_model=FeedbackResponse)
@audited(action="feedback.submit", resource_type="feedback")
async def submit_feedback(
    body: FeedbackCreate,
    auth: AuthDep,
    feedback_adapter: InvestigationFeedbackAdapterDep,
) -> FeedbackResponse:
    """Submit feedback on a hypothesis, query, evidence, synthesis, or investigation."""
    event_type = TARGET_TYPE_TO_EVENT[body.target_type]

    event = await feedback_adapter.emit(
        tenant_id=auth.tenant_id,
        event_type=event_type,
        event_data={
            "target_id": str(body.target_id),
            "rating": body.rating,
            "reason": body.reason,
            "comment": body.comment,
        },
        investigation_id=body.investigation_id,
        actor_id=auth.user_id if hasattr(auth, "user_id") else None,
        actor_type="user",
    )

    return FeedbackResponse(id=event.id, created_at=event.created_at)


class FeedbackItem(BaseModel):
    """A single feedback item returned from the API."""

    id: UUID
    target_type: str
    target_id: UUID
    rating: int
    reason: str | None
    comment: str | None
    created_at: datetime


@router.get("/investigations/{investigation_id}", response_model=list[FeedbackItem])
async def get_investigation_feedback(
    investigation_id: UUID,
    auth: AuthDep,
    db: DbDep,
) -> list[FeedbackItem]:
    """Get current user's feedback for an investigation.

    Args:
        investigation_id: The investigation to get feedback for.
        auth: Authentication context.
        db: Application database.

    Returns:
        List of feedback items for the investigation.
    """
    events = await db.list_feedback_events(
        tenant_id=auth.tenant_id,
        investigation_id=investigation_id,
    )

    # Filter to only feedback events and current user
    user_id = auth.user_id if hasattr(auth, "user_id") else None
    feedback_events = [
        e
        for e in events
        if e["event_type"].startswith("feedback.")
        and (user_id is None or e.get("actor_id") == user_id)
    ]

    result = []
    for e in feedback_events:
        # Parse event_data if it's a JSON string
        event_data = e["event_data"]
        if isinstance(event_data, str):
            event_data = json.loads(event_data)

        result.append(
            FeedbackItem(
                id=e["id"],
                target_type=e["event_type"].replace("feedback.", ""),
                target_id=UUID(str(event_data["target_id"])),
                rating=event_data["rating"],
                reason=event_data.get("reason"),
                comment=event_data.get("comment"),
                created_at=e["created_at"],
            )
        )
    return result
