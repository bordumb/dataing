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
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from dataing.adapters.db import EvidenceRepository, RunRepository
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    verify_api_key,
)
from dataing.temporal.client import TemporalInvestigationClient

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


def get_temporal_client(request: Request) -> TemporalInvestigationClient:
    """Get the Temporal client from app state.

    Args:
        request: FastAPI request object.

    Returns:
        TemporalInvestigationClient instance.

    Raises:
        HTTPException: If Temporal client is not configured.
    """
    client: TemporalInvestigationClient | None = getattr(
        request.app.state, "temporal_client", None
    )
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Temporal client not configured. Set INVESTIGATION_ENGINE=temporal.",
        )
    return client


# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AppDbDep = Annotated[Any, Depends(get_app_db)]
TemporalClientDep = Annotated[TemporalInvestigationClient, Depends(get_temporal_client)]

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
    db: AppDbDep,
    temporal_client: TemporalClientDep,
) -> RunResponse:
    """Create and start a new investigation run.

    This is the one-call API that accepts either:
    - bundle_id: Use an existing bundle
    - bundle: Inline bundle specification (assets will be resolved)

    Exactly one of bundle_id or bundle must be provided.
    """
    from dataing.entrypoints.api.deps import resolve_datasource_id

    # Require at least bundle (for asset info) - bundle_id is optional for caching
    if not body.bundle:
        raise HTTPException(
            status_code=422,
            detail="bundle is required (contains asset information for investigation)",
        )

    run_id = uuid4()
    now = datetime.now(UTC)

    # Create bundle via bundles API
    from dataing.entrypoints.api.routes.bundles import (
        AssetRefRequest as BundleAssetRefRequest,
    )
    from dataing.entrypoints.api.routes.bundles import (
        CreateBundleRequest,
        create_bundle,
    )

    bundle_assets = [
        BundleAssetRefRequest(
            platform=a.platform,
            name=a.name,
            datasource_id=a.datasource_id,
        )
        for a in body.bundle.assets
    ]
    bundle_request = CreateBundleRequest(
        assets=bundle_assets,
        window=body.bundle.window,
    )
    # Create a mock response object for the bundle endpoint
    bundle_response_obj = Response()
    bundle_result = await create_bundle(
        request, bundle_request, auth, bundle_response_obj
    )
    bundle_id = bundle_result.bundle_id
    bundle_hash = bundle_result.bundle_hash
    assets_list = [
        {"platform": a.platform, "name": a.name, "datasource_id": a.datasource_id}
        for a in body.bundle.assets
    ]

    # Resolve datasource_id from assets or use default
    datasource_id = None
    if assets_list:
        for asset in assets_list:
            if asset.get("datasource_id"):
                datasource_id = asset["datasource_id"]
                break

    if not datasource_id:
        try:
            datasource_id = await resolve_datasource_id(request, auth.tenant_id, None)
        except ValueError:
            # No default datasource, use a placeholder for demo
            datasource_id = UUID("00000000-0000-0000-0000-000000000003")

    # Build dataset_ids from assets
    # Extract just the table name from qualified names like "demo.main.orders" -> "orders"
    dataset_ids = []
    if assets_list:
        for a in assets_list:
            name = a.get("name", "unknown")
            # Take the last part of qualified name (e.g., "demo.main.orders" -> "orders")
            table_name = name.split(".")[-1] if "." in name else name
            dataset_ids.append(table_name)

    # Create a simple alert structure for goal-based investigation
    alert_data = {
        "dataset_ids": dataset_ids,
        "metric_spec": {
            "metric_type": "description",
            "expression": body.goal,
            "display_name": "User Query",
            "columns_referenced": [],
        },
        "anomaly_type": "user_query",
        "expected_value": 0.0,
        "actual_value": 0.0,
        "deviation_pct": 0.0,
        "anomaly_date": now.date().isoformat(),
        "severity": "medium",
        "datasource_id": str(datasource_id),
    }

    # Persist run via repository
    app_db = request.app.state.app_db
    run_repo = RunRepository(app_db)

    # Create run record in database
    await run_repo.create_run(
        run_id=run_id,
        tenant_id=auth.tenant_id,
        bundle_id=UUID(bundle_id) if bundle_id else None,
        bundle_hash=bundle_hash,
        goal=body.goal,
    )

    # Store in-memory cache for real-time streaming
    _run_metadata[str(run_id)] = {
        "run_id": str(run_id),
        "bundle_id": bundle_id,
        "bundle_hash": bundle_hash,
        "status": RunStatus.RUNNING.value,
        "goal": body.goal,
        "created_at": now.isoformat(),
        "tenant_id": str(auth.tenant_id),
    }

    # Store initial event (both in-memory and database)
    _store_event(
        str(run_id),
        SSEEventType.RUN_STARTED.value,
        {"goal": body.goal, "bundle_id": bundle_id},
    )
    await run_repo.store_event(
        run_id=run_id,
        seq=1,
        event_type=SSEEventType.RUN_STARTED.value,
        data={"goal": body.goal, "bundle_id": bundle_id},
    )

    try:
        # Save investigation to database
        await db.execute(
            """
            INSERT INTO investigations (id, tenant_id, alert)
            VALUES ($1, $2, $3)
            """,
            run_id,
            auth.tenant_id,
            json.dumps(alert_data),
        )

        # Start the Temporal workflow
        alert_summary = f"User query: {body.goal}"
        if dataset_ids:
            alert_summary += f" (on {', '.join(dataset_ids)})"

        await temporal_client.start_investigation(
            investigation_id=str(run_id),
            tenant_id=str(auth.tenant_id),
            datasource_id=str(datasource_id),
            alert_data=alert_data,
            alert_summary=alert_summary,
        )

        logger.info(f"Started Temporal run: run_id={run_id}, tenant_id={auth.tenant_id}")

    except Exception as e:
        logger.error(f"Failed to start Temporal run: {e}")
        _run_metadata[str(run_id)]["status"] = RunStatus.FAILED.value
        _store_event(
            str(run_id),
            SSEEventType.RUN_FAILED.value,
            {"error": str(e)},
        )
        # Update database
        await run_repo.update_run_status(run_id, RunStatus.FAILED.value)
        max_seq = await run_repo.get_max_seq(run_id)
        await run_repo.store_event(
            run_id=run_id,
            seq=max_seq + 1,
            event_type=SSEEventType.RUN_FAILED.value,
            data={"error": str(e)},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start investigation: {e}",
        ) from e

    # Build events URL
    events_url = f"/api/v1/runs/{run_id}/events"

    return RunResponse(
        run_id=str(run_id),
        bundle_id=bundle_id,
        bundle_hash=bundle_hash,
        status=RunStatus.RUNNING,
        events_url=events_url,
        created_at=now,
    )


@router.get("/{run_id}/events")
async def stream_events(
    request: Request,
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
    # Get repository for database access
    app_db = request.app.state.app_db
    run_repo = RunRepository(app_db)

    # Check if run exists (in memory or database)
    run_uuid = UUID(run_id)
    run_record = await run_repo.get_run(run_uuid)
    in_memory = run_id in _run_metadata

    if not run_record and not in_memory:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Check replay window (only for in-memory runs)
    if in_memory and _is_replay_window_expired(run_id):
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
            if in_memory and _is_replay_window_expired(run_id):
                logger.info("run_events_replay_expired", run_id=run_id)
                break

            # Try database first, fall back to in-memory
            db_events = await run_repo.get_events_after(run_uuid, last_seq)
            if db_events:
                new_events = db_events
            else:
                new_events = _get_events_after(run_id, last_seq)

            for event in new_events:
                last_seq = event["seq"]
                yield {
                    "event": event["event"],
                    "id": str(event["seq"]),
                    "data": json.dumps(event),
                }

            # Check if run is complete (check database first, then in-memory)
            current_run = await run_repo.get_run(run_uuid)
            if current_run and current_run["status"] in [s.value for s in TERMINAL_STATUSES]:
                break

            if in_memory:
                metadata = _run_metadata.get(run_id, {})
                status = metadata.get("status")
                if status in [s.value for s in TERMINAL_STATUSES]:
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
    request: Request,
    run_id: str,
    auth: AuthDep,
) -> dict[str, Any]:
    """Get run status and metadata."""
    # Get repository for database access
    app_db = request.app.state.app_db
    run_repo = RunRepository(app_db)
    run_uuid = UUID(run_id)

    # Check database first
    run_record = await run_repo.get_run(run_uuid)
    in_memory = run_id in _run_metadata

    if not run_record and not in_memory:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Build metadata from database record or in-memory
    if run_record:
        metadata = {
            "run_id": run_record["run_id"],
            "bundle_id": run_record["bundle_id"],
            "bundle_hash": run_record["bundle_hash"],
            "status": run_record["status"],
            "goal": run_record["goal"],
            "created_at": (
                run_record["created_at"].isoformat() if run_record["created_at"] else None
            ),
            "tenant_id": run_record["tenant_id"],
        }
    else:
        metadata = _run_metadata[run_id].copy()

    # Try to get real status from Temporal and sync to database
    try:
        temporal_client: TemporalInvestigationClient | None = getattr(
            request.app.state, "temporal_client", None
        )
        if temporal_client:
            temporal_status = await temporal_client.get_status(run_id)
            workflow_status = temporal_status.workflow_status
            new_status = None
            if workflow_status == "completed":
                new_status = RunStatus.COMPLETED.value
            elif workflow_status == "failed":
                new_status = RunStatus.FAILED.value
            elif workflow_status == "cancelled":
                new_status = RunStatus.CANCELLED.value

            if new_status and new_status != metadata.get("status"):
                metadata["status"] = new_status
                # Update in-memory cache
                if in_memory:
                    _run_metadata[run_id]["status"] = new_status
                # Update database
                await run_repo.update_run_status(run_uuid, new_status)
    except Exception as e:
        # Log but don't fail - return cached status
        logger.debug(f"Could not get Temporal status for {run_id}: {e}")

    return metadata


@router.post("/{run_id}/cancel")
async def cancel_run(
    request: Request,
    run_id: str,
    auth: AuthDep,
) -> dict[str, Any]:
    """Cancel a running investigation."""
    # Get repository for database access
    app_db = request.app.state.app_db
    run_repo = RunRepository(app_db)
    run_uuid = UUID(run_id)

    # Check database and in-memory
    run_record = await run_repo.get_run(run_uuid)
    in_memory = run_id in _run_metadata

    if not run_record and not in_memory:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Check current status
    current_status = run_record["status"] if run_record else _run_metadata[run_id]["status"]
    if current_status in [s.value for s in TERMINAL_STATUSES]:
        return {"status": "already_complete", "run_id": run_id}

    # Update in-memory status
    if in_memory:
        _run_metadata[run_id]["status"] = RunStatus.CANCELLED.value
        _run_metadata[run_id]["completed_at"] = datetime.now(UTC).isoformat()

    # Store cancelled event in memory
    _store_event(
        run_id,
        SSEEventType.RUN_FAILED.value,
        {"reason": "cancelled"},
    )

    # Update database
    await run_repo.update_run_status(run_uuid, RunStatus.CANCELLED.value)
    max_seq = await run_repo.get_max_seq(run_uuid)
    await run_repo.store_event(
        run_id=run_uuid,
        seq=max_seq + 1,
        event_type=SSEEventType.RUN_FAILED.value,
        data={"reason": "cancelled"},
    )

    return {"status": "cancelled", "run_id": run_id}


# --- Evidence Storage Models ---


class StoreEvidenceRequest(BaseModel):
    """Request to store evidence for a run."""

    kind: str = Field(..., description="Evidence kind discriminator")
    content: dict[str, Any] = Field(..., description="Evidence content")


class EvidenceResponse(BaseModel):
    """Response for stored evidence."""

    id: str
    run_id: str
    seq: int
    kind: str
    content_hash: str
    prev_hash: str | None = None
    created_at: datetime


# --- Evidence Endpoints ---


@router.post("/{run_id}/evidence", response_model=EvidenceResponse)
async def store_evidence(
    request: Request,
    run_id: str,
    body: StoreEvidenceRequest,
    auth: AuthDep,
) -> EvidenceResponse:
    """Store evidence for a run.

    Evidence is stored with tamper-evident hash chain.
    """
    import hashlib

    app_db = request.app.state.app_db
    run_repo = RunRepository(app_db)
    evidence_repo = EvidenceRepository(app_db)
    run_uuid = UUID(run_id)

    # Verify run exists
    run_record = await run_repo.get_run(run_uuid)
    if not run_record:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Get next sequence number and previous hash
    max_seq = await evidence_repo.get_max_seq(run_uuid)
    prev_hash = await evidence_repo.get_latest_hash(run_uuid)
    next_seq = max_seq + 1

    # Compute content hash
    content_json = json.dumps(body.content, sort_keys=True, default=str)
    content_hash = hashlib.sha256(content_json.encode()).hexdigest()

    # Store evidence
    evidence_record = await evidence_repo.store_evidence(
        run_id=run_uuid,
        seq=next_seq,
        kind=body.kind,
        content=body.content,
        content_hash=content_hash,
        prev_hash=prev_hash,
    )

    return EvidenceResponse(
        id=evidence_record["id"],
        run_id=evidence_record["run_id"],
        seq=evidence_record["seq"],
        kind=evidence_record["kind"],
        content_hash=evidence_record["content_hash"],
        prev_hash=evidence_record["prev_hash"],
        created_at=evidence_record["created_at"],
    )


@router.get("/{run_id}/evidence", response_model=list[dict[str, Any]])
async def get_evidence(
    request: Request,
    run_id: str,
    auth: AuthDep,
    kind: str | None = Query(default=None, description="Filter by evidence kind"),
) -> list[dict[str, Any]]:
    """Get evidence for a run, optionally filtered by kind."""
    app_db = request.app.state.app_db
    evidence_repo = EvidenceRepository(app_db)
    run_uuid = UUID(run_id)

    evidence_list = await evidence_repo.get_evidence_by_run(run_uuid, kind)
    return evidence_list
