"""Steering a running investigation (docs/specs/0001_issue_chat.md §7.8).

A steer is stored pending, shown in the issue thread, then signalled to the
workflow, which applies it at its next checkpoint and records the outcome. When
the signal can't be delivered (the run already finished), the steer is recorded
as rejected here.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, model_validator

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.investigation_steers import InvestigationSteerRepository
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing.entrypoints.api.routes.investigations import (
    TemporalClientDep,
    TenantInvestigationId,
    get_app_db,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/investigations", tags=["investigations"])

AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]

NOT_RUNNING = "The investigation isn't running: use Continue investigating"

SteerKind = Literal["add_context", "rule_out", "add_hypothesis", "stop_and_synthesize"]


class SteerCreate(BaseModel):
    """A steer for a running investigation."""

    kind: SteerKind
    text: str = Field(default="", max_length=2000)
    hypothesis_id: str | None = Field(default=None, max_length=64)
    # The agent reply whose proposal this steer sends; sending it again is a no-op
    proposal_message_id: UUID | None = None

    @model_validator(mode="after")
    def _needs_what_it_acts_on(self) -> SteerCreate:
        if self.kind in ("add_context", "add_hypothesis") and not self.text.strip():
            raise ValueError(f"A {self.kind} steer needs text")
        if self.kind == "rule_out" and not (self.text.strip() or self.hypothesis_id):
            raise ValueError("A rule_out steer needs a hypothesis_id or text")
        return self


class SteerResponse(BaseModel):
    """A steer and how it ended."""

    id: UUID
    investigation_id: UUID
    issue_id: UUID | None
    message_id: UUID | None
    kind: str
    text: str
    hypothesis_id: str | None
    actor_user_id: UUID | None
    status: str  # pending | applied | rejected
    applied_phase: str | None
    outcome: str | None
    created_at: datetime
    applied_at: datetime | None


class SteerListResponse(BaseModel):
    """An investigation's steers, oldest first."""

    items: list[SteerResponse]


@router.post("/{investigation_id}/steers", response_model=SteerResponse, status_code=201)
async def create_steer(
    auth: WriteScopeDep,  # First, so a viewer is refused before the lookup
    investigation_id: TenantInvestigationId,
    body: SteerCreate,
    db: AppDbDep,
    temporal_client: TemporalClientDep,
    response: Response,
) -> SteerResponse:
    """Send a steer to a running investigation."""
    steers = InvestigationSteerRepository(db)
    if body.proposal_message_id is not None:
        sent = await steers.find_by_proposal(investigation_id, body.proposal_message_id)
        if sent is not None:
            response.status_code = 200
            return SteerResponse(**sent)

    run = await db.fetch_one(
        "SELECT issue_id FROM issue_investigation_runs WHERE investigation_id = $1",
        investigation_id,
    )
    steer = await steers.create(
        tenant_id=auth.tenant_id,
        investigation_id=investigation_id,
        issue_id=run["issue_id"] if run else None,
        kind=body.kind,
        text=body.text.strip(),
        hypothesis_id=body.hypothesis_id,
        actor_user_id=auth.user_id,
        proposal_message_id=body.proposal_message_id,
    )
    try:
        await temporal_client.steer_investigation(
            str(investigation_id),
            {
                "steer_id": str(steer["id"]),
                "kind": steer["kind"],
                "text": steer["text"],
                "hypothesis_id": steer["hypothesis_id"],
                "actor_user_id": str(auth.user_id) if auth.user_id else None,
            },
        )
    except Exception as e:
        logger.info(f"Steer {steer['id']} not delivered to {investigation_id}: {e}")
        await steers.record_outcome(
            steer["id"], status="rejected", phase="finished", outcome=NOT_RUNNING
        )
        steer = await steers.get(steer["id"]) or steer
    return SteerResponse(**steer)


@router.get("/{investigation_id}/steers", response_model=SteerListResponse)
async def list_steers(
    auth: AuthDep,
    investigation_id: TenantInvestigationId,
    db: AppDbDep,
) -> SteerListResponse:
    """List an investigation's steers with their status and outcome."""
    rows = await InvestigationSteerRepository(db).list_for_investigation(investigation_id)
    return SteerListResponse(items=[SteerResponse(**row) for row in rows])
