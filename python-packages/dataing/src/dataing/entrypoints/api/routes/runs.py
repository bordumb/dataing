"""Runs API endpoints.

This module provides the API for creating and streaming investigation runs,
which are bound to context bundles.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    verify_api_key,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]

# SSE configuration
HEARTBEAT_INTERVAL_SECONDS = 30
REPLAY_WINDOW_SECONDS = 300  # 5 minutes


# --- Enums ---


class RunStatus(str, Enum):
    """Status of a run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class SSEEventType(str, Enum):
    """External SSE event types (run_* prefix)."""

    RUN_STARTED = "run_started"
    RUN_PROGRESS = "run_progress"
    RUN_EVIDENCE = "run_evidence"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_HEARTBEAT = "run_heartbeat"


# Internal to external event mapping
INTERNAL_TO_EXTERNAL_EVENT = {
    "investigation.started": SSEEventType.RUN_STARTED,
    "investigation.completed": SSEEventType.RUN_COMPLETED,
    "investigation.failed": SSEEventType.RUN_FAILED,
    "hypothesis.generated": SSEEventType.RUN_PROGRESS,
    "hypothesis.accepted": SSEEventType.RUN_EVIDENCE,
    "hypothesis.rejected": SSEEventType.RUN_PROGRESS,
    "query.submitted": SSEEventType.RUN_PROGRESS,
    "query.succeeded": SSEEventType.RUN_EVIDENCE,
    "query.failed": SSEEventType.RUN_PROGRESS,
}


# --- Request/Response Models ---


class AssetRefRequest(BaseModel):
    """Asset reference in request."""

    platform: str
    name: str
    datasource_id: str | None = None


class InlineBundleRequest(BaseModel):
    """Inline bundle specification for one-call API."""

    assets: list[AssetRefRequest]
    window: str | None = None


class CreateRunRequest(BaseModel):
    """Request to create a run.

    Accepts exactly one of bundle_id or bundle (inline).
    """

    goal: str = Field(..., description="Investigation goal/question")
    bundle_id: str | None = Field(
        default=None, description="Existing bundle ID to use"
    )
    bundle: InlineBundleRequest | None = Field(
        default=None, description="Inline bundle specification"
    )


class RunResponse(BaseModel):
    """Response for a created run."""

    run_id: str
    bundle_id: str
    bundle_hash: str
    status: RunStatus
    events_url: str
    created_at: datetime


class StreamEventResponse(BaseModel):
    """SSE stream event."""

    seq: int = Field(..., description="Resume cursor (integer)")
    event: str
    run_id: str
    data: dict[str, Any]
    timestamp: datetime


# --- In-memory event store (placeholder for real implementation) ---

# In production, this would be backed by Redis or a database
_run_events: dict[str, list[dict[str, Any]]] = {}
_run_metadata: dict[str, dict[str, Any]] = {}


def _store_event(run_id: str, event_type: str, data: dict[str, Any]) -> int:
    """Store an event and return its sequence number."""
    if run_id not in _run_events:
        _run_events[run_id] = []

    seq = len(_run_events[run_id]) + 1
    event = {
        "seq": seq,
        "event": event_type,
        "run_id": run_id,
        "data": data,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    _run_events[run_id].append(event)
    return seq


def _get_events_after(run_id: str, after_seq: int) -> list[dict[str, Any]]:
    """Get events after a sequence number."""
    events = _run_events.get(run_id, [])
    return [e for e in events if e["seq"] > after_seq]


def _is_replay_window_expired(run_id: str) -> bool:
    """Check if the replay window has expired for a run."""
    metadata = _run_metadata.get(run_id)
    if not metadata:
        return True

    completed_at = metadata.get("completed_at")
    if not completed_at:
        return False  # Run still active

    # Check if more than REPLAY_WINDOW_SECONDS have passed
    completed_dt = datetime.fromisoformat(completed_at)
    elapsed = (datetime.now(UTC) - completed_dt).total_seconds()
    return elapsed > REPLAY_WINDOW_SECONDS


# --- Endpoints ---


@router.post("", response_model=RunResponse)
async def create_run(
    request: Request,
    body: CreateRunRequest,
    auth: AuthDep,
) -> RunResponse:
    """Create and start a new investigation run.

    This is the one-call API that accepts either:
    - bundle_id: Use an existing bundle
    - bundle: Inline bundle specification (assets will be resolved)

    Exactly one of bundle_id or bundle must be provided.
    """
    # Validate exactly one of bundle_id or bundle
    if body.bundle_id and body.bundle:
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of bundle_id or bundle, not both",
        )
    if not body.bundle_id and not body.bundle:
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of bundle_id or bundle",
        )

    run_id = str(uuid4())
    now = datetime.now(UTC)

    # Handle inline bundle
    if body.bundle:
        # Create bundle via bundles API
        from dataing.entrypoints.api.routes.bundles import (
            CreateBundleRequest,
            create_bundle,
        )

        bundle_request = CreateBundleRequest(
            assets=body.bundle.assets,  # type: ignore[arg-type]
            window=body.bundle.window,
        )
        # Create a mock response object for the bundle endpoint
        bundle_response_obj = Response()
        bundle_result = await create_bundle(
            request, bundle_request, auth, bundle_response_obj
        )
        bundle_id = bundle_result.bundle_id
        bundle_hash = bundle_result.bundle_hash
    else:
        # Use existing bundle_id
        bundle_id = body.bundle_id  # type: ignore[assignment]
        # In a real implementation, we'd look up the bundle to get its hash
        bundle_hash = f"hash-{bundle_id[:8]}"

    # Store run metadata
    _run_metadata[run_id] = {
        "run_id": run_id,
        "bundle_id": bundle_id,
        "bundle_hash": bundle_hash,
        "status": RunStatus.RUNNING.value,
        "goal": body.goal,
        "created_at": now.isoformat(),
        "tenant_id": str(auth.tenant_id),
    }

    # Store initial event
    _store_event(
        run_id,
        SSEEventType.RUN_STARTED.value,
        {"goal": body.goal, "bundle_id": bundle_id},
    )

    # In a real implementation, this would start the investigation workflow
    # For now, we just return the run info

    # Build events URL
    events_url = f"/api/v1/runs/{run_id}/events"

    return RunResponse(
        run_id=run_id,
        bundle_id=bundle_id,
        bundle_hash=bundle_hash,
        status=RunStatus.RUNNING,
        events_url=events_url,
        created_at=now,
    )


@router.get("/{run_id}/events")
async def stream_events(
    run_id: str,
    auth: AuthDep,
    last_event_id: int | None = Query(
        default=None, alias="seq", description="Resume from this sequence number"
    ),
) -> EventSourceResponse:
    """Stream SSE events for a run.

    Events have an integer `seq` field for resumption.
    Use `?seq=N` to resume from sequence N.

    Returns 410 Gone if the replay window has expired.
    """
    # Check if run exists
    if run_id not in _run_metadata:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Check replay window
    if _is_replay_window_expired(run_id):
        raise HTTPException(
            status_code=410,
            detail="Replay window expired. Events are no longer available.",
        )

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        """Generate SSE events."""
        last_seq = last_event_id or 0
        last_heartbeat = datetime.now(UTC)

        while True:
            # Check if replay window expired (for completed runs)
            if _is_replay_window_expired(run_id):
                logger.info("run_events_replay_expired", run_id=run_id)
                break

            # Get new events
            new_events = _get_events_after(run_id, last_seq)

            for event in new_events:
                last_seq = event["seq"]
                yield {
                    "event": event["event"],
                    "id": str(event["seq"]),
                    "data": json.dumps(event),
                }

            # Check if run is complete
            metadata = _run_metadata.get(run_id, {})
            status = metadata.get("status")
            if status in [s.value for s in TERMINAL_STATUSES]:
                # Send final event and close
                break

            # Send heartbeat if needed
            now = datetime.now(UTC)
            if (now - last_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL_SECONDS:
                last_heartbeat = now
                heartbeat_data = {
                    "seq": last_seq,
                    "event": SSEEventType.RUN_HEARTBEAT.value,
                    "run_id": run_id,
                    "data": {},
                    "timestamp": now.isoformat(),
                }
                yield {
                    "event": SSEEventType.RUN_HEARTBEAT.value,
                    "id": str(last_seq),
                    "data": json.dumps(heartbeat_data),
                }

            # Wait before checking for more events
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@router.get("/{run_id}", response_model=dict[str, Any])
async def get_run(
    run_id: str,
    auth: AuthDep,
) -> dict[str, Any]:
    """Get run status and metadata."""
    if run_id not in _run_metadata:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    return _run_metadata[run_id]


@router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    auth: AuthDep,
) -> dict[str, Any]:
    """Cancel a running investigation."""
    if run_id not in _run_metadata:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    metadata = _run_metadata[run_id]
    if metadata["status"] in [s.value for s in TERMINAL_STATUSES]:
        return {"status": "already_complete", "run_id": run_id}

    # Update status
    metadata["status"] = RunStatus.CANCELLED.value
    metadata["completed_at"] = datetime.now(UTC).isoformat()

    # Store cancelled event
    _store_event(
        run_id,
        SSEEventType.RUN_FAILED.value,
        {"reason": "cancelled"},
    )

    return {"status": "cancelled", "run_id": run_id}
