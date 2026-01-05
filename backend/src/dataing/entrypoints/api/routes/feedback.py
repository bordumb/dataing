"""API routes for user feedback collection."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


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
