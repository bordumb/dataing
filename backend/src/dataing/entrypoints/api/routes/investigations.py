"""API routes for the investigation service."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any, cast

if TYPE_CHECKING:
    from dataing.adapters.datasource.sql.base import SQLAdapter

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dataing.core.domain_types import AnomalyAlert
from dataing.core.orchestrator import InvestigationOrchestrator
from dataing.core.state import InvestigationState
from dataing.entrypoints.api.deps import (
    get_context_engine_for_tenant,
    get_default_tenant_adapter,
    get_investigations,
    get_orchestrator,
    get_tenant_lineage_adapter,
)
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/investigations", tags=["investigations"])

logger = structlog.get_logger()

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
OrchestratorDep = Annotated[InvestigationOrchestrator, Depends(get_orchestrator)]
InvestigationsDep = Annotated[dict[str, dict[str, Any]], Depends(get_investigations)]


class CreateInvestigationRequest(BaseModel):
    """Request body for creating an investigation."""

    dataset_id: str
    metric_name: str
    expected_value: float
    actual_value: float
    deviation_pct: float
    anomaly_date: str
    severity: str = "medium"
    metadata: dict[str, str | int | float | bool] | None = None


class InvestigationResponse(BaseModel):
    """Response for investigation creation."""

    investigation_id: str
    status: str
    created_at: datetime


class InvestigationStatusResponse(BaseModel):
    """Response for investigation status."""

    investigation_id: str
    status: str
    events: list[dict[str, Any]]
    finding: dict[str, Any] | None = None
    error: str | None = None


@router.post("/", response_model=InvestigationResponse)
async def create_investigation(
    http_request: Request,
    request: CreateInvestigationRequest,
    background_tasks: BackgroundTasks,
    auth: AuthDep,
    orchestrator: OrchestratorDep,
    investigations: InvestigationsDep,
) -> InvestigationResponse:
    """Start a new investigation.

    This endpoint starts an investigation in the background
    and returns immediately with the investigation ID.

    The investigation will query the tenant's actual data source
    (e.g., DuckDB with parquet files) instead of just metadata.
    """
    investigation_id = str(uuid.uuid4())

    alert = AnomalyAlert(
        dataset_id=request.dataset_id,
        metric_name=request.metric_name,
        expected_value=request.expected_value,
        actual_value=request.actual_value,
        deviation_pct=request.deviation_pct,
        anomaly_date=request.anomaly_date,
        severity=request.severity,
        metadata=request.metadata,
    )

    state = InvestigationState(
        id=investigation_id,
        tenant_id=auth.tenant_id,
        alert=alert,
    )

    # Store initial state
    investigations[investigation_id] = {
        "state": state,
        "finding": None,
        "status": "started",
        "created_at": datetime.now(UTC),
        "tenant_id": str(auth.tenant_id),
    }

    # Run investigation in background with tenant's data source
    async def run_investigation() -> None:
        try:
            # Resolve tenant's data source adapter using AdapterRegistry
            data_adapter = await get_default_tenant_adapter(http_request, auth.tenant_id)

            # Get tenant's lineage adapter if configured
            lineage_adapter = await get_tenant_lineage_adapter(http_request, auth.tenant_id)

            # Create context engine with tenant's lineage adapter
            context_engine = get_context_engine_for_tenant(http_request, lineage_adapter)

            # Update orchestrator with tenant-specific context engine
            orchestrator.context_engine = context_engine

            # Run investigation against tenant's actual data
            # Cast to SQLAdapter since investigations require SQL capabilities
            sql_adapter = cast("SQLAdapter", data_adapter)
            finding = await orchestrator.run_investigation(state, sql_adapter)
            investigations[investigation_id]["finding"] = finding.model_dump()
            investigations[investigation_id]["status"] = "completed"
        except Exception as e:
            import traceback

            logger.error("investigation_failed", error=str(e), traceback=traceback.format_exc())
            investigations[investigation_id]["status"] = "failed"
            investigations[investigation_id]["error"] = str(e)

    background_tasks.add_task(run_investigation)

    return InvestigationResponse(
        investigation_id=investigation_id,
        status="started",
        created_at=datetime.now(UTC),
    )


@router.get("/{investigation_id}")
async def get_investigation(
    investigation_id: str,
    auth: AuthDep,
    investigations: InvestigationsDep,
) -> InvestigationStatusResponse:
    """Get investigation status and results."""
    if investigation_id not in investigations:
        raise HTTPException(status_code=404, detail="Investigation not found")

    inv = investigations[investigation_id]

    # Check tenant access
    if inv.get("tenant_id") and inv["tenant_id"] != str(auth.tenant_id):
        raise HTTPException(status_code=404, detail="Investigation not found")

    state: InvestigationState = inv["state"]

    return InvestigationStatusResponse(
        investigation_id=state.id,
        status=inv["status"],
        events=[
            {
                "type": e.type,
                "timestamp": e.timestamp.isoformat(),
                "data": e.data,
            }
            for e in state.events
        ],
        finding=inv.get("finding"),
        error=inv.get("error"),
    )


@router.get("/{investigation_id}/events")
async def stream_events(
    investigation_id: str,
    auth: AuthDep,
    investigations: InvestigationsDep,
) -> StreamingResponse:
    """SSE stream of investigation events.

    Returns a Server-Sent Events stream that pushes
    new events as they occur during the investigation.
    """
    if investigation_id not in investigations:
        raise HTTPException(status_code=404, detail="Investigation not found")

    inv = investigations[investigation_id]

    # Check tenant access
    if inv.get("tenant_id") and inv["tenant_id"] != str(auth.tenant_id):
        raise HTTPException(status_code=404, detail="Investigation not found")

    async def event_generator() -> AsyncIterator[str]:
        """Generate SSE events."""
        last_event_count = 0

        while True:
            inv = investigations.get(investigation_id)
            if not inv:
                break

            state: InvestigationState = inv["state"]
            current_events = state.events

            # Send new events
            if len(current_events) > last_event_count:
                for event in current_events[last_event_count:]:
                    event_data = {
                        "type": event.type,
                        "timestamp": event.timestamp.isoformat(),
                        "data": event.data,
                    }
                    yield f"data: {event_data}\n\n"
                last_event_count = len(current_events)

            # Check if investigation is complete
            if inv["status"] in ("completed", "failed"):
                yield f'data: {{"type": "investigation_ended", "status": "{inv["status"]}"}}\n\n'
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.get("")
async def list_investigations(
    auth: AuthDep,
    investigations: InvestigationsDep,
) -> list[dict[str, Any]]:
    """List all investigations for the current tenant."""
    tenant_id = str(auth.tenant_id)

    return [
        {
            "investigation_id": inv_id,
            "status": inv["status"],
            "created_at": inv["created_at"].isoformat(),
            "dataset_id": inv["state"].alert.dataset_id,
        }
        for inv_id, inv in investigations.items()
        if not inv.get("tenant_id") or inv["tenant_id"] == tenant_id
    ]
