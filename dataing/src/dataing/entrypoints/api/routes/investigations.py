"""API routes for the unified investigation system.

This module provides endpoints for the investigation system
with branch support and real-time updates via SSE streaming.

Supports multiple investigation engines via INVESTIGATION_ENGINE env var:
- "arq" (default): Legacy Arq-based job queue
- "temporal": Durable Temporal workflow execution
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.service import InvestigationService
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.deps import settings
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.temporal.client import TemporalInvestigationClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/investigations", tags=["investigations"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]


class StartInvestigationRequest(BaseModel):
    """Request body for starting an investigation."""

    alert: dict[str, Any]  # AnomalyAlert data
    datasource_id: UUID | None = None  # Optional datasource ID for durable execution


class StartInvestigationResponse(BaseModel):
    """Response for starting an investigation."""

    investigation_id: UUID
    main_branch_id: UUID
    status: str = "queued"


class CancelInvestigationResponse(BaseModel):
    """Response for cancelling an investigation."""

    investigation_id: UUID
    status: str  # "cancelling" or "already_complete"
    jobs_cancelled: int = 0


class StepHistoryItemResponse(BaseModel):
    """A step in the branch history."""

    step: str
    completed: bool
    timestamp: str | None = None


class MatchedPatternResponse(BaseModel):
    """A pattern that was matched during investigation."""

    pattern_id: str
    pattern_name: str
    confidence: float
    description: str | None = None


class BranchStateResponse(BaseModel):
    """State of a branch for API responses."""

    branch_id: UUID
    status: str
    current_step: str
    synthesis: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = []
    step_history: list[StepHistoryItemResponse] = []
    matched_patterns: list[MatchedPatternResponse] = []
    can_merge: bool = False
    parent_branch_id: UUID | None = None


class InvestigationStateResponse(BaseModel):
    """Full investigation state for API responses."""

    investigation_id: UUID
    status: str
    main_branch: BranchStateResponse
    user_branch: BranchStateResponse | None = None


class InvestigationListItem(BaseModel):
    """Investigation list item for API responses."""

    investigation_id: UUID
    status: str
    created_at: str
    dataset_id: str


class SendMessageRequest(BaseModel):
    """Request body for sending a message."""

    message: str


class SendMessageResponse(BaseModel):
    """Response for sending a message."""

    branch_id: UUID


class TemporalStatusResponse(BaseModel):
    """Status response for Temporal-based investigations."""

    investigation_id: str
    workflow_status: str
    current_step: str | None = None
    progress: float | None = None
    is_complete: bool | None = None
    is_cancelled: bool | None = None
    is_awaiting_user: bool | None = None
    hypotheses_count: int | None = None
    hypotheses_evaluated: int | None = None
    evidence_count: int | None = None


class UserInputRequest(BaseModel):
    """Request body for sending user input to an investigation."""

    feedback: str
    action: str | None = None
    data: dict[str, Any] | None = None


def get_investigation_service(request: Request) -> InvestigationService:
    """Get the investigation service from app state.

    Args:
        request: The current request.

    Returns:
        The configured InvestigationService.

    Raises:
        HTTPException: If service is not configured.
    """
    service: InvestigationService | None = getattr(request.app.state, "investigation_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Investigation service not configured",
        )
    return service


InvestigationServiceDep = Annotated[InvestigationService, Depends(get_investigation_service)]


def get_app_db(request: Request) -> AppDatabase:
    """Get the app database from app state."""
    app_db: AppDatabase = request.app.state.app_db
    return app_db


AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


def get_temporal_client(request: Request) -> TemporalInvestigationClient | None:
    """Get the Temporal client from app state if available.

    Args:
        request: The current request.

    Returns:
        TemporalInvestigationClient if configured, None otherwise.
    """
    return getattr(request.app.state, "temporal_client", None)


TemporalClientDep = Annotated[TemporalInvestigationClient | None, Depends(get_temporal_client)]


def is_temporal_engine() -> bool:
    """Check if Temporal engine is configured."""
    return settings.INVESTIGATION_ENGINE == "temporal"


@router.get("", response_model=list[InvestigationListItem])
async def list_investigations(
    auth: AuthDep,
    db: AppDbDep,
) -> list[InvestigationListItem]:
    """List all investigations for the tenant.

    Args:
        auth: Authentication context from API key/JWT.
        db: Application database.

    Returns:
        List of investigations.
    """
    try:
        results = await db.fetch_all(
            """
            SELECT id,
                   alert,
                   created_at,
                   COALESCE(outcome->>'status', status) AS status
            FROM investigations
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT 100
            """,
            auth.tenant_id,
        )
    except Exception as e:
        logger.error(f"Failed to list investigations: {e}")
        return []

    items = []
    for row in results:
        alert_data = row["alert"]
        if isinstance(alert_data, str):
            alert_data = json.loads(alert_data)

        items.append(
            InvestigationListItem(
                investigation_id=row["id"],
                status=row.get("status", "active"),
                created_at=row["created_at"].isoformat(),
                dataset_id=alert_data.get("dataset_id", "unknown"),
            )
        )

    return items


@router.post("", response_model=StartInvestigationResponse)
async def start_investigation(
    http_request: Request,
    request: StartInvestigationRequest,
    auth: AuthDep,
    service: InvestigationServiceDep,
    temporal_client: TemporalClientDep,
) -> StartInvestigationResponse:
    """Start a new investigation for an alert.

    Creates a new investigation with a main branch positioned at
    GATHER_CONTEXT step.

    Uses Temporal workflow when INVESTIGATION_ENGINE=temporal, otherwise
    falls back to the legacy investigation service.

    Args:
        http_request: The HTTP request for accessing app state.
        request: The investigation request containing alert data.
        auth: Authentication context from API key/JWT.
        service: Investigation service dependency.
        temporal_client: Optional Temporal client for durable execution.

    Returns:
        StartInvestigationResponse with investigation and branch IDs.
    """
    from uuid import uuid4

    from dataing.entrypoints.api.deps import get_tenant_adapter, resolve_datasource_id

    # Parse alert from request
    alert_data = request.alert
    metric_spec_data = alert_data.get("metric_spec", {})

    metric_spec = MetricSpec(
        metric_type=metric_spec_data.get("metric_type", "column"),
        expression=metric_spec_data.get("expression", ""),
        display_name=metric_spec_data.get("display_name", ""),
        columns_referenced=metric_spec_data.get("columns_referenced", []),
        source_url=metric_spec_data.get("source_url"),
    )

    alert = AnomalyAlert(
        dataset_id=alert_data["dataset_id"],
        metric_spec=metric_spec,
        anomaly_type=alert_data["anomaly_type"],
        expected_value=alert_data["expected_value"],
        actual_value=alert_data["actual_value"],
        deviation_pct=alert_data["deviation_pct"],
        anomaly_date=alert_data["anomaly_date"],
        severity=alert_data.get("severity", "medium"),
        source_system=alert_data.get("source_system"),
        source_alert_id=alert_data.get("source_alert_id"),
        source_url=alert_data.get("source_url"),
        metadata=alert_data.get("metadata"),
    )

    # Resolve datasource_id (use provided or get default)
    try:
        datasource_id = await resolve_datasource_id(
            http_request, auth.tenant_id, request.datasource_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e

    # Use Temporal workflow if configured and client is available
    if is_temporal_engine() and temporal_client is not None:
        investigation_id = uuid4()
        alert_summary = f"{alert.anomaly_type} in {alert.dataset_id}"

        try:
            await temporal_client.start_investigation(
                investigation_id=str(investigation_id),
                tenant_id=str(auth.tenant_id),
                datasource_id=str(datasource_id),
                alert_data=alert.model_dump(),
                alert_summary=alert_summary,
            )
            logger.info(
                f"Started Temporal investigation: investigation_id={investigation_id}, "
                f"tenant_id={auth.tenant_id}"
            )
            return StartInvestigationResponse(
                investigation_id=investigation_id,
                main_branch_id=investigation_id,  # Temporal uses single workflow ID
                status="queued",
            )
        except Exception as e:
            logger.error(f"Failed to start Temporal investigation: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start investigation: {e}",
            ) from e

    # Fall back to legacy investigation service
    # Get data adapter for this tenant
    try:
        data_adapter = await get_tenant_adapter(http_request, auth.tenant_id, datasource_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not get data adapter: {e}",
        ) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Data adapter error: {e}",
        ) from e

    # Extract correlation ID from middleware for distributed tracing
    correlation_id = getattr(http_request.state, "correlation_id", None)

    investigation_id, main_branch_id, status = await service.start_investigation(
        tenant_id=auth.tenant_id,
        alert=alert,
        data_adapter=data_adapter,
        user_id=auth.user_id,
        datasource_id=datasource_id,
        correlation_id=correlation_id,
    )

    return StartInvestigationResponse(
        investigation_id=investigation_id,
        main_branch_id=main_branch_id,
        status=status,
    )


@router.post("/{investigation_id}/cancel", response_model=CancelInvestigationResponse)
async def cancel_investigation(
    http_request: Request,
    investigation_id: UUID,
    auth: AuthDep,
    temporal_client: TemporalClientDep,
) -> CancelInvestigationResponse:
    """Cancel an investigation and all its child jobs.

    For Temporal engine: Sends cancel signal to the workflow.
    For legacy engine: Marks the investigation job as 'cancelling'.

    Args:
        http_request: The HTTP request for accessing app state.
        investigation_id: UUID of the investigation to cancel.
        auth: Authentication context from API key/JWT.
        temporal_client: Optional Temporal client for durable execution.

    Returns:
        CancelInvestigationResponse with cancellation status.

    Raises:
        HTTPException: If investigation not found or already complete.
    """
    # Use Temporal workflow if configured and client is available
    if is_temporal_engine() and temporal_client is not None:
        try:
            await temporal_client.cancel_investigation(str(investigation_id))
            logger.info(
                f"Sent cancel signal to Temporal investigation: "
                f"investigation_id={investigation_id}, tenant_id={auth.tenant_id}"
            )
            return CancelInvestigationResponse(
                investigation_id=investigation_id,
                status="cancelling",
                jobs_cancelled=1,  # Temporal handles child workflow cancellation
            )
        except Exception as e:
            logger.error(f"Failed to cancel Temporal investigation: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to cancel investigation: {e}",
            ) from e

    # Fall back to legacy cancellation
    # Get database from app state
    app_db: AppDatabase | None = http_request.app.state.app_db

    if app_db is None:
        raise HTTPException(
            status_code=500,
            detail="Database not configured",
        )

    # Cancel investigation and all child jobs
    jobs_cancelled = await app_db.cancel_investigation_with_children(
        investigation_id=investigation_id,
        tenant_id=auth.tenant_id,
    )

    if jobs_cancelled > 0:
        logger.info(
            f"Investigation cancelled: investigation_id={investigation_id}, "
            f"tenant_id={auth.tenant_id}, jobs_cancelled={jobs_cancelled}"
        )
        return CancelInvestigationResponse(
            investigation_id=investigation_id,
            status="cancelling",
            jobs_cancelled=jobs_cancelled,
        )

    # Check if investigation exists but is already complete
    job = await app_db.get_investigation_job(investigation_id)
    if job and job.get("status") in ("completed", "failed", "cancelled"):
        return CancelInvestigationResponse(
            investigation_id=investigation_id,
            status="already_complete",
            jobs_cancelled=0,
        )

    raise HTTPException(
        status_code=404,
        detail="Investigation job not found",
    )


@router.get("/{investigation_id}", response_model=InvestigationStateResponse)
async def get_investigation(
    investigation_id: UUID,
    auth: AuthDep,
    service: InvestigationServiceDep,
) -> InvestigationStateResponse:
    """Get investigation state including user branch if exists.

    Returns the current state of the investigation with the main branch
    and optionally the user's branch if one exists.

    Args:
        investigation_id: UUID of the investigation.
        auth: Authentication context from API key/JWT.
        service: Investigation service dependency.

    Returns:
        InvestigationStateResponse with main and optional user branch.

    Raises:
        HTTPException: If investigation not found.
    """
    if auth.user_id is None:
        raise HTTPException(
            status_code=400,
            detail="User authentication required for investigation state",
        )

    try:
        state = await service.get_state(
            investigation_id=investigation_id,
            user_id=auth.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # Convert service state to API response
    main_branch = BranchStateResponse(
        branch_id=state.main_branch.branch_id,
        status=state.main_branch.status,
        current_step=state.main_branch.current_step,
        synthesis=state.main_branch.synthesis,
        evidence=list(state.main_branch.evidence),
        step_history=[
            StepHistoryItemResponse(step=s.step, completed=s.completed, timestamp=s.timestamp)
            for s in state.main_branch.step_history
        ],
        matched_patterns=[
            MatchedPatternResponse(
                pattern_id=p.pattern_id,
                pattern_name=p.pattern_name,
                confidence=p.confidence,
                description=p.description,
            )
            for p in state.main_branch.matched_patterns
        ],
        can_merge=state.main_branch.can_merge,
        parent_branch_id=state.main_branch.parent_branch_id,
    )

    user_branch = None
    if state.user_branch:
        user_branch = BranchStateResponse(
            branch_id=state.user_branch.branch_id,
            status=state.user_branch.status,
            current_step=state.user_branch.current_step,
            synthesis=state.user_branch.synthesis,
            evidence=list(state.user_branch.evidence),
            step_history=[
                StepHistoryItemResponse(step=s.step, completed=s.completed, timestamp=s.timestamp)
                for s in state.user_branch.step_history
            ],
            matched_patterns=[
                MatchedPatternResponse(
                    pattern_id=p.pattern_id,
                    pattern_name=p.pattern_name,
                    confidence=p.confidence,
                    description=p.description,
                )
                for p in state.user_branch.matched_patterns
            ],
            can_merge=state.user_branch.can_merge,
            parent_branch_id=state.user_branch.parent_branch_id,
        )

    return InvestigationStateResponse(
        investigation_id=state.investigation_id,
        status=state.status,
        main_branch=main_branch,
        user_branch=user_branch,
    )


@router.post("/{investigation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    investigation_id: UUID,
    request: SendMessageRequest,
    auth: AuthDep,
    service: InvestigationServiceDep,
) -> SendMessageResponse:
    """Send a message to the user's branch (creates branch if needed).

    Gets or creates a user branch and adds the message. Resumes the
    branch if it was suspended.

    Args:
        investigation_id: UUID of the investigation.
        request: The message request.
        auth: Authentication context from API key/JWT.
        service: Investigation service dependency.

    Returns:
        SendMessageResponse with the branch ID.

    Raises:
        HTTPException: If user authentication required.
    """
    if auth.user_id is None:
        raise HTTPException(
            status_code=400,
            detail="User authentication required to send messages",
        )

    try:
        branch_id = await service.send_message(
            investigation_id=investigation_id,
            user_id=auth.user_id,
            message=request.message,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return SendMessageResponse(branch_id=branch_id)


@router.get("/{investigation_id}/status", response_model=TemporalStatusResponse)
async def get_investigation_status(
    investigation_id: UUID,
    auth: AuthDep,
    temporal_client: TemporalClientDep,
) -> TemporalStatusResponse:
    """Get the status of an investigation.

    For Temporal engine: Queries the workflow for real-time progress.
    For legacy engine: Returns basic status from database.

    Args:
        investigation_id: UUID of the investigation.
        auth: Authentication context from API key/JWT.
        temporal_client: Optional Temporal client for durable execution.

    Returns:
        TemporalStatusResponse with current progress and state.
    """
    if is_temporal_engine() and temporal_client is not None:
        try:
            status = await temporal_client.get_status(str(investigation_id))
            return TemporalStatusResponse(
                investigation_id=status.workflow_id,
                workflow_status=status.workflow_status,
                current_step=status.current_step,
                progress=status.progress,
                is_complete=status.is_complete,
                is_cancelled=status.is_cancelled,
                is_awaiting_user=status.is_awaiting_user,
                hypotheses_count=status.hypotheses_count,
                hypotheses_evaluated=status.hypotheses_evaluated,
                evidence_count=status.evidence_count,
            )
        except Exception as e:
            logger.error(f"Failed to get Temporal investigation status: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get investigation status: {e}",
            ) from e

    # Legacy fallback - return basic status
    raise HTTPException(
        status_code=501,
        detail="Status endpoint only available for Temporal engine. "
        "Use GET /investigations/{id} for legacy investigations.",
    )


@router.post("/{investigation_id}/input")
async def send_user_input(
    investigation_id: UUID,
    request: UserInputRequest,
    auth: AuthDep,
    temporal_client: TemporalClientDep,
) -> dict[str, str]:
    """Send user input to an investigation awaiting feedback.

    This endpoint is only available for Temporal-based investigations
    when the workflow is in AWAIT_USER state.

    Args:
        investigation_id: UUID of the investigation.
        request: User input payload.
        auth: Authentication context from API key/JWT.
        temporal_client: Optional Temporal client for durable execution.

    Returns:
        Confirmation message.
    """
    if not is_temporal_engine() or temporal_client is None:
        raise HTTPException(
            status_code=501,
            detail="User input endpoint only available for Temporal engine.",
        )

    try:
        payload = {
            "feedback": request.feedback,
            "action": request.action,
            "data": request.data or {},
            "user_id": str(auth.user_id) if auth.user_id else None,
        }
        await temporal_client.send_user_input(str(investigation_id), payload)
        logger.info(
            f"Sent user input to Temporal investigation: "
            f"investigation_id={investigation_id}, tenant_id={auth.tenant_id}"
        )
        return {"status": "input_received", "investigation_id": str(investigation_id)}
    except Exception as e:
        logger.error(f"Failed to send user input to Temporal investigation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send user input: {e}",
        ) from e


@router.get("/{investigation_id}/stream")
async def stream_updates(
    investigation_id: UUID,
    auth: AuthDep,
    service: InvestigationServiceDep,
) -> EventSourceResponse:
    """Stream real-time updates via SSE.

    Returns a Server-Sent Events stream that pushes investigation
    updates as they occur.

    Args:
        investigation_id: UUID of the investigation.
        auth: Authentication context from API key/JWT.
        service: Investigation service dependency.

    Returns:
        EventSourceResponse with SSE stream.
    """
    if auth.user_id is None:
        raise HTTPException(
            status_code=400,
            detail="User authentication required for streaming",
        )

    # Capture user_id for closure (mypy type narrowing)
    user_id = auth.user_id

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        """Generate SSE events for investigation updates."""
        last_step = None
        last_status = None
        poll_count = 0
        max_polls = 600  # 5 minutes at 0.5s intervals

        try:
            while poll_count < max_polls:
                try:
                    state = await service.get_state(
                        investigation_id=investigation_id,
                        user_id=user_id,
                    )

                    # Check for changes
                    current_step = state.main_branch.current_step
                    current_status = state.status

                    if current_step != last_step:
                        yield {
                            "event": "step_changed",
                            "data": to_json_string(
                                {
                                    "step": current_step,
                                    "branch_id": str(state.main_branch.branch_id),
                                }
                            ),
                        }
                        last_step = current_step

                    if current_status != last_status:
                        yield {
                            "event": "status_changed",
                            "data": to_json_string(
                                {
                                    "status": current_status,
                                    "investigation_id": str(state.investigation_id),
                                }
                            ),
                        }
                        last_status = current_status

                    # Check for completion
                    if current_status in ("completed", "failed", "cancelled", "inconclusive"):
                        # Send final state
                        yield {
                            "event": "investigation_ended",
                            "data": to_json_string(
                                {
                                    "status": current_status,
                                    "synthesis": state.main_branch.synthesis,
                                }
                            ),
                        }
                        break

                except ValueError:
                    # Investigation not found
                    yield {
                        "event": "error",
                        "data": to_json_string(
                            {
                                "error": "Investigation not found",
                            }
                        ),
                    }
                    break

                await asyncio.sleep(0.5)
                poll_count += 1

            # Timeout
            if poll_count >= max_polls:
                yield {
                    "event": "timeout",
                    "data": to_json_string(
                        {
                            "message": "Stream timeout, please reconnect",
                        }
                    ),
                }

        except asyncio.CancelledError:
            # Client disconnected
            logger.info(f"SSE stream cancelled for investigation {investigation_id}")

    return EventSourceResponse(event_generator())
