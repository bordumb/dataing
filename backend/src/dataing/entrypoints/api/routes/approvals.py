"""Human-in-the-loop approval routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalRequestResponse(BaseModel):
    """Response for an approval request."""

    id: str
    investigation_id: str
    request_type: str
    context: dict[str, Any]
    requested_at: datetime
    requested_by: str
    decision: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    comment: str | None = None
    modifications: dict[str, Any] | None = None
    # Additional investigation context
    dataset_id: str | None = None
    metric_name: str | None = None
    severity: str | None = None


class PendingApprovalsResponse(BaseModel):
    """Response for listing pending approvals."""

    approvals: list[ApprovalRequestResponse]
    total: int


class ApproveRequest(BaseModel):
    """Request to approve an investigation."""

    comment: str | None = Field(None, max_length=1000)


class RejectRequest(BaseModel):
    """Request to reject an investigation."""

    reason: str = Field(..., min_length=1, max_length=1000)


class ModifyRequest(BaseModel):
    """Request to approve with modifications."""

    comment: str | None = Field(None, max_length=1000)
    modifications: dict[str, Any] = Field(...)


class ApprovalDecisionResponse(BaseModel):
    """Response for an approval decision."""

    id: str
    investigation_id: str
    decision: str
    decided_by: str
    decided_at: datetime
    comment: str | None = None


class CreateApprovalRequest(BaseModel):
    """Request to create a new approval request."""

    investigation_id: UUID
    request_type: str = Field(..., pattern="^(context_review|query_approval|execution_approval)$")
    context: dict[str, Any] = Field(...)


@router.get("/pending", response_model=PendingApprovalsResponse)
async def list_pending_approvals(
    auth: ApiKeyContext = Depends(verify_api_key),
    app_db: AppDatabase = Depends(get_app_db),
) -> PendingApprovalsResponse:
    """List all pending approval requests for this tenant."""
    approvals = await app_db.get_pending_approvals(auth.tenant_id)

    return PendingApprovalsResponse(
        approvals=[
            ApprovalRequestResponse(
                id=str(a["id"]),
                investigation_id=str(a["investigation_id"]),
                request_type=a["request_type"],
                context=a["context"] if isinstance(a["context"], dict) else {},
                requested_at=a["requested_at"],
                requested_by=a["requested_by"],
                decision=a.get("decision"),
                decided_by=str(a["decided_by"]) if a.get("decided_by") else None,
                decided_at=a.get("decided_at"),
                comment=a.get("comment"),
                modifications=a.get("modifications"),
                dataset_id=a.get("dataset_id"),
                metric_name=a.get("metric_name"),
                severity=a.get("severity"),
            )
            for a in approvals
        ],
        total=len(approvals),
    )


@router.get("/{approval_id}", response_model=ApprovalRequestResponse)
async def get_approval_request(
    approval_id: UUID,
    auth: ApiKeyContext = Depends(verify_api_key),
    app_db: AppDatabase = Depends(get_app_db),
) -> ApprovalRequestResponse:
    """Get approval request details including context to review."""
    # Get all pending approvals and find the one with matching ID
    approvals = await app_db.get_pending_approvals(auth.tenant_id)
    approval = next((a for a in approvals if str(a["id"]) == str(approval_id)), None)

    if not approval:
        # Also check completed approvals
        result = await app_db.fetch_one(
            """SELECT ar.*, i.dataset_id, i.metric_name, i.severity
               FROM approval_requests ar
               JOIN investigations i ON i.id = ar.investigation_id
               WHERE ar.id = $1 AND ar.tenant_id = $2""",
            approval_id,
            auth.tenant_id,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Approval request not found")
        approval = result

    return ApprovalRequestResponse(
        id=str(approval["id"]),
        investigation_id=str(approval["investigation_id"]),
        request_type=approval["request_type"],
        context=approval["context"] if isinstance(approval["context"], dict) else {},
        requested_at=approval["requested_at"],
        requested_by=approval["requested_by"],
        decision=approval.get("decision"),
        decided_by=str(approval["decided_by"]) if approval.get("decided_by") else None,
        decided_at=approval.get("decided_at"),
        comment=approval.get("comment"),
        modifications=approval.get("modifications"),
        dataset_id=approval.get("dataset_id"),
        metric_name=approval.get("metric_name"),
        severity=approval.get("severity"),
    )


@router.post("/{approval_id}/approve", response_model=ApprovalDecisionResponse)
async def approve_request(
    approval_id: UUID,
    request: ApproveRequest,
    background_tasks: BackgroundTasks,
    auth: ApiKeyContext = Depends(require_scope("write")),
    app_db: AppDatabase = Depends(get_app_db),
) -> ApprovalDecisionResponse:
    """Approve an investigation to proceed."""
    user_id = auth.user_id or auth.key_id

    result = await app_db.make_approval_decision(
        approval_id=approval_id,
        tenant_id=auth.tenant_id,
        decision="approved",
        decided_by=user_id,
        comment=request.comment,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Approval request not found")

    # TODO: Resume investigation in background
    # background_tasks.add_task(resume_investigation, result["investigation_id"])

    return ApprovalDecisionResponse(
        id=str(result["id"]),
        investigation_id=str(result["investigation_id"]),
        decision="approved",
        decided_by=str(user_id),
        decided_at=result["decided_at"],
        comment=result.get("comment"),
    )


@router.post("/{approval_id}/reject", response_model=ApprovalDecisionResponse)
async def reject_request(
    approval_id: UUID,
    request: RejectRequest,
    auth: ApiKeyContext = Depends(require_scope("write")),
    app_db: AppDatabase = Depends(get_app_db),
) -> ApprovalDecisionResponse:
    """Reject an investigation."""
    user_id = auth.user_id or auth.key_id

    result = await app_db.make_approval_decision(
        approval_id=approval_id,
        tenant_id=auth.tenant_id,
        decision="rejected",
        decided_by=user_id,
        comment=request.reason,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Approval request not found")

    # Update investigation status to cancelled
    await app_db.update_investigation_status(
        result["investigation_id"],
        status="cancelled",
    )

    return ApprovalDecisionResponse(
        id=str(result["id"]),
        investigation_id=str(result["investigation_id"]),
        decision="rejected",
        decided_by=str(user_id),
        decided_at=result["decided_at"],
        comment=request.reason,
    )


@router.post("/{approval_id}/modify", response_model=ApprovalDecisionResponse)
async def modify_and_approve(
    approval_id: UUID,
    request: ModifyRequest,
    background_tasks: BackgroundTasks,
    auth: ApiKeyContext = Depends(require_scope("write")),
    app_db: AppDatabase = Depends(get_app_db),
) -> ApprovalDecisionResponse:
    """Approve with modifications.

    This allows reviewers to modify the investigation context before approving.
    For example, they can adjust which tables are included, modify query limits, etc.
    """
    user_id = auth.user_id or auth.key_id

    result = await app_db.make_approval_decision(
        approval_id=approval_id,
        tenant_id=auth.tenant_id,
        decision="modified",
        decided_by=user_id,
        comment=request.comment,
        modifications=request.modifications,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Approval request not found")

    # TODO: Resume investigation with modifications
    # background_tasks.add_task(resume_investigation, result["investigation_id"], request.modifications)

    return ApprovalDecisionResponse(
        id=str(result["id"]),
        investigation_id=str(result["investigation_id"]),
        decision="modified",
        decided_by=str(user_id),
        decided_at=result["decided_at"],
        comment=result.get("comment"),
    )


@router.post("/", response_model=ApprovalRequestResponse, status_code=201)
async def create_approval_request(
    request: CreateApprovalRequest,
    auth: ApiKeyContext = Depends(require_scope("write")),
    app_db: AppDatabase = Depends(get_app_db),
) -> ApprovalRequestResponse:
    """Create a new approval request.

    This is typically called by the system when an investigation reaches
    a point requiring human review (e.g., context review before executing queries).
    """
    # Verify investigation exists and belongs to tenant
    investigation = await app_db.get_investigation(request.investigation_id, auth.tenant_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    result = await app_db.create_approval_request(
        investigation_id=request.investigation_id,
        tenant_id=auth.tenant_id,
        request_type=request.request_type,
        context=request.context,
        requested_by="system",
    )

    return ApprovalRequestResponse(
        id=str(result["id"]),
        investigation_id=str(result["investigation_id"]),
        request_type=result["request_type"],
        context=result["context"] if isinstance(result["context"], dict) else {},
        requested_at=result["requested_at"],
        requested_by=result["requested_by"],
        dataset_id=investigation.get("dataset_id"),
        metric_name=investigation.get("metric_name"),
        severity=investigation.get("severity"),
    )


@router.get("/investigation/{investigation_id}", response_model=list[ApprovalRequestResponse])
async def get_investigation_approvals(
    investigation_id: UUID,
    auth: ApiKeyContext = Depends(verify_api_key),
    app_db: AppDatabase = Depends(get_app_db),
) -> list[ApprovalRequestResponse]:
    """Get all approval requests for a specific investigation."""
    # Verify investigation exists and belongs to tenant
    investigation = await app_db.get_investigation(investigation_id, auth.tenant_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    results = await app_db.fetch_all(
        """SELECT * FROM approval_requests
           WHERE investigation_id = $1 AND tenant_id = $2
           ORDER BY requested_at DESC""",
        investigation_id,
        auth.tenant_id,
    )

    return [
        ApprovalRequestResponse(
            id=str(a["id"]),
            investigation_id=str(a["investigation_id"]),
            request_type=a["request_type"],
            context=a["context"] if isinstance(a["context"], dict) else {},
            requested_at=a["requested_at"],
            requested_by=a["requested_by"],
            decision=a.get("decision"),
            decided_by=str(a["decided_by"]) if a.get("decided_by") else None,
            decided_at=a.get("decided_at"),
            comment=a.get("comment"),
            modifications=a.get("modifications"),
            dataset_id=investigation.get("dataset_id"),
            metric_name=investigation.get("metric_name"),
            severity=investigation.get("severity"),
        )
        for a in results
    ]
