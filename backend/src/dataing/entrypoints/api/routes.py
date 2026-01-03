"""API routes for the investigation service."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dataing.core.domain_types import AnomalyAlert
from dataing.core.orchestrator import InvestigationOrchestrator
from dataing.core.state import InvestigationState

from .deps import get_investigations, get_orchestrator

router = APIRouter()


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


@router.post("/investigations", response_model=InvestigationResponse)
async def create_investigation(
    request: CreateInvestigationRequest,
    background_tasks: BackgroundTasks,
    orchestrator: InvestigationOrchestrator = Depends(get_orchestrator),
    investigations: dict = Depends(get_investigations),
) -> InvestigationResponse:
    """Start a new investigation.

    This endpoint starts an investigation in the background
    and returns immediately with the investigation ID.
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

    state = InvestigationState(id=investigation_id, alert=alert)

    # Store initial state
    investigations[investigation_id] = {
        "state": state,
        "finding": None,
        "status": "started",
        "created_at": datetime.now(timezone.utc),
    }

    # Run investigation in background
    async def run_investigation() -> None:
        try:
            finding = await orchestrator.run_investigation(state)
            investigations[investigation_id]["finding"] = finding.model_dump()
            investigations[investigation_id]["status"] = "completed"
        except Exception as e:
            investigations[investigation_id]["status"] = "failed"
            investigations[investigation_id]["error"] = str(e)

    background_tasks.add_task(run_investigation)

    return InvestigationResponse(
        investigation_id=investigation_id,
        status="started",
        created_at=datetime.now(timezone.utc),
    )


@router.get("/investigations/{investigation_id}")
async def get_investigation(
    investigation_id: str,
    investigations: dict = Depends(get_investigations),
) -> InvestigationStatusResponse:
    """Get investigation status and results."""
    if investigation_id not in investigations:
        raise HTTPException(status_code=404, detail="Investigation not found")

    inv = investigations[investigation_id]
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
    )


@router.get("/investigations/{investigation_id}/events")
async def stream_events(
    investigation_id: str,
    investigations: dict = Depends(get_investigations),
) -> StreamingResponse:
    """SSE stream of investigation events.

    Returns a Server-Sent Events stream that pushes
    new events as they occur during the investigation.
    """
    if investigation_id not in investigations:
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
                yield f"data: {{\"type\": \"investigation_ended\", \"status\": \"{inv['status']}\"}}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.get("/investigations")
async def list_investigations(
    investigations: dict = Depends(get_investigations),
) -> list[dict[str, Any]]:
    """List all investigations."""
    return [
        {
            "investigation_id": inv_id,
            "status": inv["status"],
            "created_at": inv["created_at"].isoformat(),
            "dataset_id": inv["state"].alert.dataset_id,
        }
        for inv_id, inv in investigations.items()
    ]
