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

from dataing.adapters.audit import audited
from dataing.adapters.db.app_db import AppDatabase
from dataing.core.domain_types import AnomalyAlert
from dataing.core.entitlements.features import Feature
from dataing.core.orchestrator import InvestigationOrchestrator
from dataing.core.rbac import PermissionService
from dataing.core.state import InvestigationState
from dataing.entrypoints.api.deps import (
    get_app_db,
    get_context_engine_for_tenant,
    get_default_tenant_adapter,
    get_investigations,
    get_orchestrator,
    get_tenant_lineage_adapter,
)
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.middleware.entitlements import require_under_limit

router = APIRouter(prefix="/investigations", tags=["investigations"])

logger = structlog.get_logger()

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
OrchestratorDep = Annotated[InvestigationOrchestrator, Depends(get_orchestrator)]
InvestigationsDep = Annotated[dict[str, dict[str, Any]], Depends(get_investigations)]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


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
@audited(action="investigation.create", resource_type="investigation")
@require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
async def create_investigation(
    request: Request,
    body: CreateInvestigationRequest,
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
        dataset_id=body.dataset_id,
        metric_name=body.metric_name,
        expected_value=body.expected_value,
        actual_value=body.actual_value,
        deviation_pct=body.deviation_pct,
        anomaly_date=body.anomaly_date,
        severity=body.severity,
        metadata=body.metadata,
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
            data_adapter = await get_default_tenant_adapter(request, auth.tenant_id)

            # Get tenant's lineage adapter if configured
            lineage_adapter = await get_tenant_lineage_adapter(request, auth.tenant_id)

            # Create context engine with tenant's lineage adapter
            context_engine = get_context_engine_for_tenant(request, lineage_adapter)

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
    app_db: AppDbDep,
    investigations: InvestigationsDep,
) -> InvestigationStatusResponse:
    """Get investigation status and results."""
    if investigation_id not in investigations:
        raise HTTPException(status_code=404, detail="Investigation not found")

    inv = investigations[investigation_id]

    # Check tenant access
    if inv.get("tenant_id") and inv["tenant_id"] != str(auth.tenant_id):
        raise HTTPException(status_code=404, detail="Investigation not found")

    # Check RBAC permissions if user_id is available and investigation is persisted
    # Note: In-memory investigations (not yet persisted) rely on tenant check above
    if auth.user_id:
        try:
            inv_uuid = uuid.UUID(investigation_id)
            async with app_db.acquire() as conn:
                # Check if investigation exists in DB before RBAC check
                exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM investigations WHERE id = $1)",
                    inv_uuid,
                )
                if exists:
                    permission_service = PermissionService(conn)
                    has_access = await permission_service.can_access_investigation(
                        auth.user_id, inv_uuid
                    )
                    if not has_access:
                        raise HTTPException(
                            status_code=403,
                            detail="You don't have access to this investigation",
                        )
                # If not in DB, rely on tenant check above (in-memory investigation)
        except ValueError:
            # Invalid UUID, fall back to tenant check only
            pass

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
    app_db: AppDbDep,
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

    # Check RBAC permissions if user_id is available and investigation is persisted
    if auth.user_id:
        try:
            inv_uuid = uuid.UUID(investigation_id)
            async with app_db.acquire() as conn:
                exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM investigations WHERE id = $1)",
                    inv_uuid,
                )
                if exists:
                    permission_service = PermissionService(conn)
                    has_access = await permission_service.can_access_investigation(
                        auth.user_id, inv_uuid
                    )
                    if not has_access:
                        raise HTTPException(
                            status_code=403,
                            detail="You don't have access to this investigation",
                        )
        except ValueError:
            pass

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
    app_db: AppDbDep,
    investigations: InvestigationsDep,
) -> list[dict[str, Any]]:
    """List all investigations for the current tenant.

    Results are filtered by RBAC permissions when user_id is available.
    Admins and owners see all investigations; members see only those
    they have access to via direct grants, tags, teams, or datasources.
    """
    tenant_id = str(auth.tenant_id)

    # First filter by tenant
    tenant_investigations = [
        (inv_id, inv)
        for inv_id, inv in investigations.items()
        if not inv.get("tenant_id") or inv["tenant_id"] == tenant_id
    ]

    # If user_id is available, apply RBAC filtering
    if auth.user_id:
        async with app_db.acquire() as conn:
            permission_service = PermissionService(conn)
            accessible_ids = await permission_service.get_accessible_investigation_ids(
                auth.user_id, auth.tenant_id
            )

            # None means admin/owner - show all
            if accessible_ids is not None:
                accessible_set = {str(id_) for id_ in accessible_ids}
                tenant_investigations = [
                    (inv_id, inv)
                    for inv_id, inv in tenant_investigations
                    if inv_id in accessible_set
                ]

    return [
        {
            "investigation_id": inv_id,
            "status": inv["status"],
            "created_at": inv["created_at"].isoformat(),
            "dataset_id": inv["state"].alert.dataset_id,
        }
        for inv_id, inv in tenant_investigations
    ]
