"""API routes for the unified investigation system.

This module provides endpoints for Temporal-based investigations
with real-time updates via SSE streaming.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing.temporal.client import TemporalInvestigationClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/investigations", tags=["investigations"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]


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
    root_hash: str | None = None


class ChainVerificationResponse(BaseModel):
    """Response from evidence chain verification."""

    investigation_id: UUID
    is_valid: bool
    evidence_count: int
    root_hash: str | None = None
    root_hash_matches: bool | None = None
    first_broken_seq: int | None = None
    error: str | None = None
    chain_available: bool = True


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

    status: str
    investigation_id: UUID


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


class CodifyFormat(str, Enum):
    """Output format for test generation."""

    GX = "gx"
    DBT = "dbt"
    SODA = "soda"
    SQL = "sql"


class CodifyRequest(BaseModel):
    """Request body for codifying an investigation."""

    format: CodifyFormat = CodifyFormat.SQL


class CodifyTestResponse(BaseModel):
    """A single test extracted from the investigation."""

    test_type: str
    column: str | None = None
    table: str
    description: str


class CodifyResponse(BaseModel):
    """Response for codifying an investigation."""

    investigation_id: UUID
    format: str
    content: str
    tests: list[CodifyTestResponse]
    confidence: float


class TestTrackingStatsResponse(BaseModel):
    """Test tracking statistics response."""

    tests_generated: int
    tests_adopted: int
    tests_run: int
    issues_caught: int
    adoption_rate: float
    effectiveness_rate: float


class TestAdoptionRequest(BaseModel):
    """Request to mark a test as adopted."""

    test_id: UUID
    adopted_by: str | None = None


class TestRunResultRequest(BaseModel):
    """Request to record a test run result."""

    test_id: UUID
    passed: bool
    failure_message: str | None = None


class RecentCatchResponse(BaseModel):
    """A recent test failure catch."""

    test_id: str
    run_at: str
    failure_message: str | None
    test_type: str
    table: str
    column: str | None
    investigation_id: str


def get_app_db(request: Request) -> AppDatabase:
    """Get the app database from app state."""
    app_db: AppDatabase = request.app.state.app_db
    return app_db


AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


def get_temporal_client(request: Request) -> TemporalInvestigationClient:
    """Get the Temporal client from app state.

    Args:
        request: The current request.

    Returns:
        TemporalInvestigationClient.

    Raises:
        HTTPException: If Temporal client is not configured.
    """
    client: TemporalInvestigationClient | None = getattr(request.app.state, "temporal_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Temporal client not configured",
        )
    return client


TemporalClientDep = Annotated[TemporalInvestigationClient, Depends(get_temporal_client)]


async def require_tenant_investigation(
    investigation_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> UUID:
    """Resolve the path investigation ID, enforcing tenant ownership.

    Missing investigations and other tenants' investigations both return the
    same 404, so callers cannot probe which investigation IDs exist.

    Args:
        investigation_id: Investigation ID from the request path.
        auth: Authentication context from API key/JWT.
        db: Application database.

    Returns:
        The investigation ID, verified to belong to the caller's tenant.

    Raises:
        HTTPException: 404 if the investigation is missing or owned by another tenant.
    """
    row = await db.fetch_one(
        "SELECT tenant_id FROM investigations WHERE id = $1",
        investigation_id,
    )
    if row is None or row["tenant_id"] != auth.tenant_id:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation not found: {investigation_id}",
        )
    return investigation_id


# Every /{investigation_id} route must take its ID through this dependency.
TenantInvestigationId = Annotated[UUID, Depends(require_tenant_investigation)]


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
                   created_at,
                   COALESCE(outcome->>'status', status) AS status,
                   -- Primary dataset, "unknown" when there is none (as AnomalyAlert.dataset_id)
                   COALESCE(alert->'dataset_ids'->>0, 'unknown') AS dataset_id
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
        items.append(
            InvestigationListItem(
                investigation_id=row["id"],
                status=row.get("status", "active"),
                created_at=row["created_at"].isoformat(),
                dataset_id=row["dataset_id"],
            )
        )

    return items


@router.post("", response_model=StartInvestigationResponse)
async def start_investigation(
    http_request: Request,
    request: StartInvestigationRequest,
    auth: WriteScopeDep,
    db: AppDbDep,
    temporal_client: TemporalClientDep,
) -> StartInvestigationResponse:
    """Start a new investigation for an alert.

    Creates a new investigation with Temporal workflow for durable execution.

    Args:
        http_request: The HTTP request for accessing app state.
        request: The investigation request containing alert data.
        auth: Authentication context from API key/JWT.
        db: Application database.
        temporal_client: Temporal client for durable execution.

    Returns:
        StartInvestigationResponse with investigation and branch IDs.
    """
    from dataing.entrypoints.api.deps import resolve_datasource_id

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

    # Handle both dataset_id (singular) and dataset_ids (plural) for backward compatibility
    dataset_ids = alert_data.get("dataset_ids")
    if dataset_ids is None:
        # Convert singular to list
        dataset_id = alert_data.get("dataset_id", "unknown")
        dataset_ids = [dataset_id] if isinstance(dataset_id, str) else dataset_id

    alert = AnomalyAlert(
        dataset_ids=dataset_ids,
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
            http_request, auth.tenant_id, explicit_id=request.datasource_id
        )
    except ValueError as e:
        error_msg = str(e)
        if error_msg.startswith("ambiguous_datasource:"):
            # Parse the ambiguous datasource error for 409 response
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "ambiguous_datasource",
                    "message": "Multiple datasources match. Please specify which to use.",
                    "hint": "Specify datasource_id or use %dataing attach",
                },
            ) from e
        raise HTTPException(
            status_code=400,
            detail=error_msg,
        ) from e

    investigation_id = uuid4()
    # Build rich alert summary with all critical information (matches main branch)
    metric_name = alert.metric_spec.display_name
    columns = ", ".join(alert.metric_spec.columns_referenced) or "unknown column"
    alert_summary = (
        f"{alert.anomaly_type} anomaly on {columns} in {alert.dataset_id}: "
        f"expected {alert.expected_value}, actual {alert.actual_value} "
        f"({alert.deviation_pct:.1f}% deviation). "
        f"Metric: {metric_name}. Date: {alert.anomaly_date}."
    )

    try:
        # Save investigation to database first (so GET /investigations/{id} works)
        # Note: The unified schema stores datasource_id in alert metadata
        # Use mode="json" to ensure dates are serialized as ISO strings
        alert_dict = alert.model_dump(mode="json")
        alert_dict["datasource_id"] = str(datasource_id)
        await db.execute(
            """
            INSERT INTO investigations (id, tenant_id, alert)
            VALUES ($1, $2, $3)
            """,
            investigation_id,
            auth.tenant_id,
            json.dumps(alert_dict),
        )

        # Start the Temporal workflow
        # Use mode="json" to ensure all values are JSON-serializable for Temporal
        await temporal_client.start_investigation(
            investigation_id=str(investigation_id),
            tenant_id=str(auth.tenant_id),
            datasource_id=str(datasource_id),
            alert_data=alert.model_dump(mode="json"),
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


@router.post("/{investigation_id}/cancel", response_model=CancelInvestigationResponse)
async def cancel_investigation(
    auth: WriteScopeDep,
    investigation_id: TenantInvestigationId,
    temporal_client: TemporalClientDep,
) -> CancelInvestigationResponse:
    """Cancel an investigation and all its child workflows.

    Args:
        investigation_id: UUID of the investigation to cancel.
        auth: Authentication context from API key/JWT.
        temporal_client: Temporal client for durable execution.

    Returns:
        CancelInvestigationResponse with cancellation status.

    Raises:
        HTTPException: If investigation not found or already complete.
    """
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


@router.get("/{investigation_id}", response_model=InvestigationStateResponse)
async def get_investigation(
    investigation_id: TenantInvestigationId,
    auth: AuthDep,
    temporal_client: TemporalClientDep,
) -> InvestigationStateResponse:
    """Get investigation state from Temporal workflow.

    Returns the current state of the investigation including progress
    and any available results.

    Args:
        investigation_id: UUID of the investigation.
        auth: Authentication context from API key/JWT.
        temporal_client: Temporal client for durable execution.

    Returns:
        InvestigationStateResponse with main branch state.

    Raises:
        HTTPException: If investigation not found.
    """
    try:
        status = await temporal_client.get_status(str(investigation_id))

        # Build response from Temporal status
        main_branch = BranchStateResponse(
            branch_id=investigation_id,
            status=status.workflow_status,
            current_step=status.current_step or "unknown",
            synthesis=status.result.synthesis if status.result else None,
            evidence=list(status.result.evidence) if status.result else [],
            step_history=[],
            matched_patterns=[],
            can_merge=False,
            parent_branch_id=None,
        )

        root_hash = getattr(status.result, "root_hash", None) if status.result else None

        return InvestigationStateResponse(
            investigation_id=investigation_id,
            status=status.workflow_status,
            main_branch=main_branch,
            user_branch=None,
            root_hash=root_hash,
        )
    except Exception as e:
        logger.error(f"Failed to get Temporal investigation: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Investigation not found: {e}",
        ) from e


@router.get("/{investigation_id}/verify", response_model=ChainVerificationResponse)
async def verify_investigation(
    investigation_id: TenantInvestigationId,
    auth: AuthDep,
    db: AppDbDep,
) -> ChainVerificationResponse:
    """Verify the integrity of an investigation's evidence hash chain.

    Validates that evidence items have not been tampered with by checking
    content hashes and chain linkage.

    Args:
        investigation_id: UUID of the investigation.
        auth: Authentication context from API key/JWT.
        db: Application database.

    Returns:
        ChainVerificationResponse with verification result.

    Raises:
        HTTPException: If investigation not found.
    """
    from dataing.adapters.db.sdk_repository import EvidenceRepository
    from dataing.core.evidence import verify_chain

    # Check investigation exists and belongs to tenant
    inv = await db.fetch_one(
        "SELECT id, root_hash FROM investigations WHERE id = $1 AND tenant_id = $2",
        investigation_id,
        auth.tenant_id,
    )
    if not inv:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation not found: {investigation_id}",
        )

    stored_root_hash: str | None = inv.get("root_hash")

    # Load evidence
    repo = EvidenceRepository(db)
    evidence_items = await repo.get_evidence_by_run(investigation_id)

    if not evidence_items:
        return ChainVerificationResponse(
            investigation_id=investigation_id,
            is_valid=True,
            evidence_count=0,
            root_hash=stored_root_hash,
            root_hash_matches=None,
            chain_available=False,
        )

    # Check if evidence has chain fields populated
    first_item = evidence_items[0]
    if not first_item.get("content_hash"):
        return ChainVerificationResponse(
            investigation_id=investigation_id,
            is_valid=True,
            evidence_count=len(evidence_items),
            root_hash=stored_root_hash,
            root_hash_matches=None,
            chain_available=False,
        )

    # Verify the chain
    is_valid, broken_seq, error_msg = verify_chain(evidence_items)

    # Compute root_hash from chain (content_hash of last item)
    computed_root_hash = evidence_items[-1].get("content_hash") if evidence_items else None

    # Compare stored vs computed root_hash
    root_hash_matches = None
    if stored_root_hash and computed_root_hash:
        root_hash_matches = stored_root_hash == computed_root_hash

    return ChainVerificationResponse(
        investigation_id=investigation_id,
        is_valid=is_valid,
        evidence_count=len(evidence_items),
        root_hash=computed_root_hash,
        root_hash_matches=root_hash_matches,
        first_broken_seq=broken_seq,
        error=error_msg,
        chain_available=True,
    )


@router.post("/{investigation_id}/codify", response_model=CodifyResponse)
async def codify_investigation(
    auth: WriteScopeDep,
    investigation_id: TenantInvestigationId,
    request: CodifyRequest,
    db: AppDbDep,
    temporal_client: TemporalClientDep,
) -> CodifyResponse:
    """Generate regression tests from an investigation's synthesis.

    Extracts testable assertions from the investigation synthesis and renders
    them to the specified format (Great Expectations, dbt, Soda, or SQL).

    Args:
        investigation_id: UUID of the investigation.
        request: Codify request with output format.
        auth: Authentication context from API key/JWT.
        db: Application database for test tracking.
        temporal_client: Temporal client for durable execution.

    Returns:
        CodifyResponse with rendered test content.

    Raises:
        HTTPException: If investigation not found or no synthesis available.
    """
    from dataing.agents.models import SynthesisResponse
    from dataing.core.codify import extract_tests_from_synthesis
    from dataing.renderers import get_renderer

    try:
        status = await temporal_client.get_status(str(investigation_id))
    except Exception as e:
        logger.error(f"Failed to get investigation for codify: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Investigation not found: {e}",
        ) from e

    if not status.result or not status.result.synthesis:
        raise HTTPException(
            status_code=400,
            detail="Investigation has no synthesis. Codify requires a completed investigation.",
        )

    synthesis_dict = status.result.synthesis
    confidence = synthesis_dict.get("confidence", 0.0)

    if confidence < 0.6:
        raise HTTPException(
            status_code=400,
            detail=f"Synthesis confidence too low ({confidence:.0%}). "
            "Codify requires at least 60% confidence.",
        )

    # Build SynthesisResponse from dict
    try:
        causal_chain = synthesis_dict.get("causal_chain", [])
        if len(causal_chain) < 2:
            causal_chain = ["Issue detected", "Symptom observed"] + causal_chain

        synthesis_response = SynthesisResponse(
            root_cause=synthesis_dict.get("root_cause"),
            confidence=confidence,
            causal_chain=causal_chain,
            estimated_onset=synthesis_dict.get("estimated_onset", "Unknown"),
            affected_scope=synthesis_dict.get("affected_scope", "Unknown scope"),
            supporting_evidence=synthesis_dict.get("supporting_evidence", []),
            contradicting_evidence=synthesis_dict.get("contradicting_evidence", []),
            recommendations=synthesis_dict.get("recommendations", []),
            summary=synthesis_dict.get("summary", ""),
            metadata=synthesis_dict.get("metadata", {}),
        )
    except Exception as e:
        logger.error(f"Failed to parse synthesis for codify: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse synthesis: {e}",
        ) from e

    # Extract table from metadata
    table = synthesis_dict.get("metadata", {}).get("dataset", "unknown_table")
    if "." in table:
        table = table.split(".")[-1]

    # Extract tests
    tests = extract_tests_from_synthesis(
        synthesis=synthesis_response,
        investigation_id=investigation_id,
        table=table,
    )

    if not tests:
        raise HTTPException(
            status_code=400,
            detail="No testable assertions found. "
            "The investigation may not have identified a clear root cause.",
        )

    # Render tests
    renderer = get_renderer(request.format.value)
    rendered = renderer.render_many(tests)

    # Track test generation
    try:
        from dataing.services.test_tracking import TestTrackingService

        tracker = TestTrackingService(db)
        for test in tests:
            await tracker.record_test_generated(
                tenant_id=auth.tenant_id,
                investigation_id=investigation_id,
                test_id=test.test_id,
                format_=request.format.value,
                test_type=test.assertion_type.value,
                table=test.table,
                column=test.column,
                description=test.description,
            )
    except Exception as e:
        # Don't fail codify if tracking fails
        logger.warning(f"Failed to track test generation: {e}")

    # Build response
    test_responses = [
        CodifyTestResponse(
            test_type=t.assertion_type.value,
            column=t.column,
            table=t.table,
            description=t.description,
        )
        for t in tests
    ]

    return CodifyResponse(
        investigation_id=investigation_id,
        format=request.format.value,
        content=rendered,
        tests=test_responses,
        confidence=confidence,
    )


@router.get("/tests/stats", response_model=TestTrackingStatsResponse)
async def get_test_tracking_stats(
    auth: AuthDep,
    db: AppDbDep,
    days: int = Query(default=30, ge=1, le=365, description="Days to look back"),
) -> TestTrackingStatsResponse:
    """Get test tracking statistics.

    Returns metrics on tests generated, adopted, and issues caught.

    Args:
        auth: Authentication context from API key/JWT.
        db: Application database.
        days: Number of days to look back.

    Returns:
        TestTrackingStatsResponse with statistics.
    """
    from dataing.services.test_tracking import TestTrackingService

    tracker = TestTrackingService(db)
    stats = await tracker.get_stats(auth.tenant_id, days=days)

    return TestTrackingStatsResponse(
        tests_generated=stats.tests_generated,
        tests_adopted=stats.tests_adopted,
        tests_run=stats.tests_run,
        issues_caught=stats.issues_caught,
        adoption_rate=stats.adoption_rate,
        effectiveness_rate=stats.effectiveness_rate,
    )


@router.get("/tests/catches", response_model=list[RecentCatchResponse])
async def get_recent_catches(
    auth: AuthDep,
    db: AppDbDep,
    limit: int = Query(default=10, ge=1, le=100, description="Maximum results"),
) -> list[RecentCatchResponse]:
    """Get recent tests that caught issues.

    Returns a list of recent test failures (issues caught).

    Args:
        auth: Authentication context from API key/JWT.
        db: Application database.
        limit: Maximum number of results.

    Returns:
        List of recent catches.
    """
    from dataing.services.test_tracking import TestTrackingService

    tracker = TestTrackingService(db)
    catches = await tracker.get_recent_catches(auth.tenant_id, limit=limit)

    return [
        RecentCatchResponse(
            test_id=c["test_id"],
            run_at=c["run_at"],
            failure_message=c["failure_message"],
            test_type=c["test_type"],
            table=c["table"],
            column=c["column"],
            investigation_id=c["investigation_id"],
        )
        for c in catches
    ]


@router.post("/tests/adopt")
async def adopt_test(
    request: TestAdoptionRequest,
    auth: WriteScopeDep,
    db: AppDbDep,
) -> dict[str, str]:
    """Mark a generated test as adopted.

    Call this when a test has been added to the user's project.

    Args:
        request: Adoption request with test ID.
        auth: Authentication context from API key/JWT.
        db: Application database.

    Returns:
        Status message.
    """
    from dataing.services.test_tracking import TestTrackingService

    tracker = TestTrackingService(db)
    success = await tracker.record_test_adopted(
        tenant_id=auth.tenant_id,
        test_id=request.test_id,
        adopted_by=request.adopted_by,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Test not found or already adopted",
        )

    return {"status": "adopted", "test_id": str(request.test_id)}


@router.post("/tests/run")
async def record_test_run(
    request: TestRunResultRequest,
    auth: WriteScopeDep,
    db: AppDbDep,
) -> dict[str, str]:
    """Record a test run result.

    Call this when a generated test has been executed.

    Args:
        request: Test run result.
        auth: Authentication context from API key/JWT.
        db: Application database.

    Returns:
        Status message.
    """
    from dataing.services.test_tracking import TestTrackingService

    tracker = TestTrackingService(db)
    await tracker.record_test_run(
        tenant_id=auth.tenant_id,
        test_id=request.test_id,
        passed=request.passed,
        failure_message=request.failure_message,
    )

    status = "passed" if request.passed else "caught_issue"
    return {"status": status, "test_id": str(request.test_id)}


@router.post("/{investigation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    auth: WriteScopeDep,
    investigation_id: TenantInvestigationId,
    request: SendMessageRequest,
    temporal_client: TemporalClientDep,
) -> SendMessageResponse:
    """Send a message to an investigation via Temporal signal.

    Args:
        investigation_id: UUID of the investigation.
        request: The message request.
        auth: Authentication context from API key/JWT.
        temporal_client: Temporal client for durable execution.

    Returns:
        SendMessageResponse with status.

    Raises:
        HTTPException: If failed to send message.
    """
    try:
        payload: dict[str, Any] = {
            "feedback": request.message,
            "action": "user_message",
            "data": {},
            "user_id": str(auth.user_id) if auth.user_id else None,
        }
        await temporal_client.send_user_input(str(investigation_id), payload)
        logger.info(
            f"Sent message to Temporal investigation: "
            f"investigation_id={investigation_id}, tenant_id={auth.tenant_id}"
        )
        return SendMessageResponse(
            status="message_sent",
            investigation_id=investigation_id,
        )
    except Exception as e:
        logger.error(f"Failed to send message to Temporal investigation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send message: {e}",
        ) from e


@router.get("/{investigation_id}/status", response_model=TemporalStatusResponse)
async def get_investigation_status(
    investigation_id: TenantInvestigationId,
    auth: AuthDep,
    temporal_client: TemporalClientDep,
) -> TemporalStatusResponse:
    """Get the status of an investigation.

    Queries the Temporal workflow for real-time progress.

    Args:
        investigation_id: UUID of the investigation.
        auth: Authentication context from API key/JWT.
        temporal_client: Temporal client for durable execution.

    Returns:
        TemporalStatusResponse with current progress and state.
    """
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


@router.post("/{investigation_id}/input")
async def send_user_input(
    auth: WriteScopeDep,
    investigation_id: TenantInvestigationId,
    request: UserInputRequest,
    temporal_client: TemporalClientDep,
) -> dict[str, str]:
    """Send user input to an investigation awaiting feedback.

    This endpoint sends a signal to the Temporal workflow when it's
    in AWAIT_USER state.

    Args:
        investigation_id: UUID of the investigation.
        request: User input payload.
        auth: Authentication context from API key/JWT.
        temporal_client: Temporal client for durable execution.

    Returns:
        Confirmation message.
    """
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
    investigation_id: TenantInvestigationId,
    auth: AuthDep,
    temporal_client: TemporalClientDep,
) -> EventSourceResponse:
    """Stream real-time updates via SSE.

    Returns a Server-Sent Events stream that pushes investigation
    updates as they occur by polling the Temporal workflow.

    Args:
        investigation_id: UUID of the investigation.
        auth: Authentication context from API key/JWT.
        temporal_client: Temporal client for durable execution.

    Returns:
        EventSourceResponse with SSE stream.
    """

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        """Generate SSE events for investigation updates."""
        last_step = None
        last_status = None
        poll_count = 0
        max_polls = 600  # 5 minutes at 0.5s intervals

        try:
            while poll_count < max_polls:
                try:
                    status = await temporal_client.get_status(str(investigation_id))

                    # Check for changes
                    current_step = status.current_step
                    current_status = status.workflow_status

                    if current_step != last_step:
                        yield {
                            "event": "step_changed",
                            "data": to_json_string(
                                {
                                    "step": current_step,
                                    "investigation_id": str(investigation_id),
                                    "progress": status.progress,
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
                                    "investigation_id": str(investigation_id),
                                    "is_awaiting_user": status.is_awaiting_user,
                                }
                            ),
                        }
                        last_status = current_status

                    # Check for completion
                    if status.is_complete or status.is_cancelled:
                        # Send final state
                        synthesis = None
                        if status.result:
                            synthesis = status.result.synthesis
                        yield {
                            "event": "investigation_ended",
                            "data": to_json_string(
                                {
                                    "status": current_status,
                                    "synthesis": synthesis,
                                    "is_cancelled": status.is_cancelled,
                                }
                            ),
                        }
                        break

                except Exception as e:
                    # Workflow query failed
                    logger.warning(f"Failed to poll investigation status: {e}")
                    yield {
                        "event": "error",
                        "data": to_json_string(
                            {
                                "error": f"Failed to get status: {e}",
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


# --- SSE Events Endpoint (unified with CLI) ---

# SSE configuration
HEARTBEAT_INTERVAL_SECONDS = 30
REPLAY_WINDOW_SECONDS = 300  # 5 minutes


class SSEEventType(str, Enum):
    """External SSE event types (run_* prefix for CLI compatibility)."""

    RUN_STARTED = "run_started"
    RUN_PROGRESS = "run_progress"
    RUN_EVIDENCE = "run_evidence"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_HEARTBEAT = "run_heartbeat"


class StreamEventResponse(BaseModel):
    """SSE stream event."""

    seq: int = Field(..., description="Resume cursor (integer)")
    event: str
    run_id: str
    data: dict[str, Any]
    timestamp: datetime


@router.get("/{investigation_id}/events")
async def stream_events(
    request: Request,
    investigation_id: TenantInvestigationId,
    auth: AuthDep,
    temporal_client: TemporalClientDep,
    last_event_id: int | None = Query(
        default=None, alias="seq", description="Resume from this sequence number"
    ),
) -> EventSourceResponse:
    """Stream SSE events for an investigation.

    Events have an integer `seq` field for resumption.
    Use `?seq=N` to resume from sequence N.

    Returns 410 Gone if the replay window has expired.

    Args:
        request: FastAPI request object.
        investigation_id: UUID of the investigation.
        auth: Authentication context from API key/JWT.
        temporal_client: Temporal client for status polling.
        last_event_id: Optional sequence number to resume from.

    Returns:
        EventSourceResponse with SSE stream.
    """

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        """Generate SSE events by polling Temporal workflow status."""
        seq = last_event_id or 0
        last_step = None
        last_heartbeat = datetime.now(UTC)

        # Send initial run_started event
        seq += 1
        started_data = {
            "seq": seq,
            "event": SSEEventType.RUN_STARTED.value,
            "run_id": str(investigation_id),
            "data": {"investigation_id": str(investigation_id)},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        yield {
            "event": SSEEventType.RUN_STARTED.value,
            "id": str(seq),
            "data": json.dumps(started_data),
        }

        while True:
            try:
                # Poll Temporal for current status
                status = await temporal_client.get_status(str(investigation_id))

                # Check for step changes and emit progress events
                current_step = status.current_step
                current_status = status.workflow_status

                if current_step and current_step != last_step:
                    seq += 1
                    progress_data = {
                        "seq": seq,
                        "event": SSEEventType.RUN_PROGRESS.value,
                        "run_id": str(investigation_id),
                        "data": {
                            "step": current_step,
                            "progress": status.progress,
                            "message": f"Step: {current_step}",
                        },
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                    yield {
                        "event": SSEEventType.RUN_PROGRESS.value,
                        "id": str(seq),
                        "data": json.dumps(progress_data),
                    }
                    last_step = current_step

                # Check for completion
                if status.is_complete or status.is_cancelled:
                    seq += 1
                    if status.is_complete:
                        event_type = SSEEventType.RUN_COMPLETED.value
                    else:
                        event_type = SSEEventType.RUN_FAILED.value
                    synthesis = None
                    if status.result:
                        synthesis = status.result.synthesis
                    completion_data = {
                        "seq": seq,
                        "event": event_type,
                        "run_id": str(investigation_id),
                        "data": {
                            "status": current_status,
                            "synthesis": synthesis,
                            "is_cancelled": status.is_cancelled,
                        },
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                    yield {
                        "event": event_type,
                        "id": str(seq),
                        "data": json.dumps(completion_data),
                    }
                    break

            except Exception as e:
                logger.warning(f"Failed to poll investigation status: {e}")
                seq += 1
                error_data = {
                    "seq": seq,
                    "event": SSEEventType.RUN_FAILED.value,
                    "run_id": str(investigation_id),
                    "data": {"error": str(e)},
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                yield {
                    "event": SSEEventType.RUN_FAILED.value,
                    "id": str(seq),
                    "data": json.dumps(error_data),
                }
                break

            # Send heartbeat if needed
            now = datetime.now(UTC)
            if (now - last_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL_SECONDS:
                last_heartbeat = now
                heartbeat_data = {
                    "seq": seq,
                    "event": SSEEventType.RUN_HEARTBEAT.value,
                    "run_id": str(investigation_id),
                    "data": {},
                    "timestamp": now.isoformat(),
                }
                yield {
                    "event": SSEEventType.RUN_HEARTBEAT.value,
                    "id": str(seq),
                    "data": json.dumps(heartbeat_data),
                }

            # Wait before polling again
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


# --- Snapshot Download Endpoint ---


class SnapshotCheckpointParam(str, Enum):
    """Valid checkpoint values for snapshot download."""

    START = "start"
    HYPOTHESIS_GENERATED = "hypothesis_generated"
    EVIDENCE_COLLECTED = "evidence_collected"
    COMPLETE = "complete"
    FAILED = "failed"


class SnapshotListItem(BaseModel):
    """Snapshot metadata for listing."""

    checkpoint: str
    captured_at: str
    storage_path: str
    size_bytes: int | None = None


class SnapshotListResponse(BaseModel):
    """Response for listing available snapshots."""

    investigation_id: UUID
    snapshots: list[SnapshotListItem]


def get_snapshot_store(request: Request) -> Any:
    """Get the snapshot store from app state.

    Args:
        request: The current request.

    Returns:
        SnapshotStore instance.

    Raises:
        HTTPException: If snapshot store is not configured.
    """
    store = getattr(request.app.state, "snapshot_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Snapshot storage not configured",
        )
    return store


SnapshotStoreDep = Annotated[Any, Depends(get_snapshot_store)]


@router.get("/{investigation_id}/snapshots")
async def list_snapshots(
    investigation_id: TenantInvestigationId,
    auth: AuthDep,
    db: AppDbDep,
) -> SnapshotListResponse:
    """List available snapshots for an investigation.

    Args:
        investigation_id: UUID of the investigation.
        auth: Authentication context from API key/JWT.
        db: Application database.

    Returns:
        SnapshotListResponse with list of available snapshots.

    Raises:
        HTTPException: If investigation not found or access denied.
    """
    # Verify investigation exists and belongs to tenant
    result = await db.fetch_one(
        """
        SELECT id, outcome
        FROM investigations
        WHERE id = $1 AND tenant_id = $2
        """,
        investigation_id,
        auth.tenant_id,
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation not found: {investigation_id}",
        )

    # Get snapshot paths from outcome if available
    outcome = result.get("outcome")
    snapshot_paths: list[str] = []
    if outcome:
        if isinstance(outcome, str):
            outcome = json.loads(outcome)
        snapshot_paths = outcome.get("snapshot_paths", [])

    snapshots = []
    for path in snapshot_paths:
        # Extract checkpoint from path (format: .../checkpoint.snapshot)
        checkpoint = path.rsplit("/", 1)[-1].replace(".snapshot", "")
        snapshots.append(
            SnapshotListItem(
                checkpoint=checkpoint,
                captured_at="",  # Would need to read from file
                storage_path=path,
            )
        )

    return SnapshotListResponse(
        investigation_id=investigation_id,
        snapshots=snapshots,
    )


@router.get("/{investigation_id}/snapshots/{checkpoint}")
async def download_snapshot(
    investigation_id: TenantInvestigationId,
    checkpoint: SnapshotCheckpointParam,
    auth: AuthDep,
    snapshot_store: SnapshotStoreDep,
    accept_encoding: str | None = Header(default=None, alias="Accept-Encoding"),
) -> Response:
    """Download a snapshot for local hydration.

    Supports streaming response for large snapshots and optional gzip compression.

    Args:
        investigation_id: UUID of the investigation.
        checkpoint: The checkpoint to download (start, hypothesis_generated, etc).
        auth: Authentication context from API key/JWT.
        snapshot_store: Snapshot storage backend.
        accept_encoding: Accept-Encoding header for compression.

    Returns:
        StreamingResponse with snapshot data.

    Raises:
        HTTPException: If investigation not found, access denied, or snapshot missing.
    """
    # Build expected storage path
    storage_path = f"{auth.tenant_id}/snapshots/{investigation_id}/{checkpoint.value}.snapshot"

    # Check if snapshot exists
    try:
        exists = await snapshot_store.exists(storage_path)
        if not exists:
            raise HTTPException(
                status_code=404,
                detail=f"Snapshot not found: {checkpoint.value}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check snapshot existence: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to access snapshot storage",
        ) from e

    # Retrieve snapshot
    try:
        snapshot = await snapshot_store.retrieve(storage_path)
    except Exception as e:
        logger.error(f"Failed to retrieve snapshot: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Snapshot not found: {checkpoint.value}",
        ) from e

    # Serialize snapshot to JSON
    try:
        data = snapshot.model_dump(mode="json")
        content = json.dumps(data, default=str).encode("utf-8")
    except Exception as e:
        logger.error(f"Failed to serialize snapshot: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to serialize snapshot",
        ) from e

    # Check if client accepts gzip
    use_gzip = accept_encoding and "gzip" in accept_encoding.lower()

    headers = {
        "X-Snapshot-Version": snapshot.version,
        "X-Snapshot-Checkpoint": checkpoint.value,
        "X-Snapshot-Investigation-Id": str(investigation_id),
    }

    if use_gzip:
        # Compress content
        compressed = gzip.compress(content, compresslevel=6)
        headers["Content-Encoding"] = "gzip"
        headers["Content-Length"] = str(len(compressed))
        return Response(
            content=compressed,
            media_type="application/octet-stream",
            headers=headers,
        )
    else:
        headers["Content-Length"] = str(len(content))
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers=headers,
        )


# --- Snapshot Archive Export/Import Endpoints (fn-39) ---


class ImportSnapshotResponse(BaseModel):
    """Response for importing a snapshot archive."""

    investigation_id: UUID
    status: str = "imported"
    original_investigation_id: str
    evidence_count: int
    is_replay: bool = True


@router.get("/{investigation_id}/snapshot")
async def export_snapshot_archive(
    investigation_id: TenantInvestigationId,
    auth: AuthDep,
    db: AppDbDep,
    temporal_client: TemporalClientDep,
) -> Response:
    """Download investigation as a snapshot tar.gz archive.

    Generates a compressed archive containing all evidence, lineage,
    and metadata needed to replay the investigation.

    Args:
        investigation_id: UUID of the investigation.
        auth: Authentication context from API key/JWT.
        db: Application database.
        temporal_client: Temporal client for durable execution.

    Returns:
        StreamingResponse with tar.gz archive.

    Raises:
        HTTPException: If investigation not found or not complete.
    """
    from fastapi.responses import StreamingResponse

    from dataing.adapters.db.sdk_repository import EvidenceRepository
    from dataing.core.exceptions import SnapshotSizeExceededError
    from dataing.core.snapshot_builder import SnapshotBuilder

    # Verify investigation exists and belongs to tenant
    result = await db.fetch_one(
        """
        SELECT id, alert, outcome, COALESCE(outcome->>'status', status) AS status
        FROM investigations
        WHERE id = $1 AND tenant_id = $2
        """,
        investigation_id,
        auth.tenant_id,
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation not found: {investigation_id}",
        )

    # Get investigation state from Temporal
    try:
        status = await temporal_client.get_status(str(investigation_id))
        investigation_state = {
            "status": status.workflow_status,
            "source_instance": None,  # Could be populated from config
            "tenant_id": str(auth.tenant_id),
        }
    except Exception as e:
        logger.warning(f"Failed to get Temporal status, using DB state: {e}")
        investigation_state = {
            "status": result.get("status", "unknown"),
            "source_instance": None,
            "tenant_id": str(auth.tenant_id),
        }

    # Load evidence from database
    repo = EvidenceRepository(db)
    evidence_items = await repo.get_evidence_by_run(investigation_id)

    # Build the archive
    builder = SnapshotBuilder(str(investigation_id))
    try:
        archive_path = await builder.build(
            investigation_state=investigation_state,
            evidence_items=evidence_items,
            lineage=None,  # TODO: Load lineage if available
            code_changes=None,  # TODO: Load code changes if available
            prompts=None,  # TODO: Load prompts if available
        )
    except SnapshotSizeExceededError as e:
        raise HTTPException(
            status_code=413,
            detail=f"Snapshot too large: {e.actual_size:,} bytes exceeds {e.max_size:,} byte limit",
        ) from e
    except Exception as e:
        logger.error(f"Failed to build snapshot archive: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build snapshot: {e}",
        ) from e

    # Stream the file
    def iterfile() -> Iterator[bytes]:
        with open(archive_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk
        # Clean up temp file after streaming
        archive_path.unlink(missing_ok=True)

    filename = f"snapshot-{investigation_id}.tar.gz"
    return StreamingResponse(
        iterfile(),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Snapshot-Investigation-Id": str(investigation_id),
        },
    )


@router.post("/import", response_model=ImportSnapshotResponse)
async def import_snapshot_archive(
    auth: WriteScopeDep,
    db: AppDbDep,
    file: Annotated[bytes, File()],
) -> ImportSnapshotResponse:
    """Import a snapshot archive as a replayed investigation.

    Validates the archive and creates a new investigation marked as a replay.

    Args:
        auth: Authentication context from API key/JWT.
        db: Application database.
        file: The uploaded tar.gz file.

    Returns:
        ImportSnapshotResponse with new investigation ID.

    Raises:
        HTTPException: If file is invalid or too large.
    """
    import tarfile
    from io import BytesIO

    from dataing.core.snapshot_schema import ArchivePaths, validate_metadata

    # Check file size (100MB default limit)
    max_size = 100 * 1024 * 1024
    if len(file) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(file):,} bytes exceeds {max_size:,} byte limit",
        )

    # Parse the archive
    try:
        with tarfile.open(fileobj=BytesIO(file), mode="r:gz") as tar:
            # Find metadata.json
            metadata_member = None
            for member in tar.getmembers():
                if member.name.endswith(ArchivePaths.METADATA):
                    metadata_member = member
                    break

            if not metadata_member:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid archive: missing metadata.json",
                )

            # Read and validate metadata
            f = tar.extractfile(metadata_member)
            if f is None:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid archive: cannot read metadata.json",
                )

            metadata_data = json.load(f)
            try:
                metadata = validate_metadata(metadata_data)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid metadata: {e}",
                ) from e

            # Create new investigation marked as replay
            new_investigation_id = uuid4()
            original_id = metadata.investigation_id

            # Store in database with replay flag; status is generated from outcome
            await db.execute(
                """
                INSERT INTO investigations (id, tenant_id, alert, outcome)
                VALUES ($1, $2, $3, $4)
                """,
                new_investigation_id,
                auth.tenant_id,
                json.dumps({"replay_of": original_id, "is_replay": True}),
                json.dumps(
                    {
                        "status": metadata.status,
                        "is_replay": True,
                        "original_investigation_id": original_id,
                        "original_created_at": metadata.created_at.isoformat()
                        if metadata.created_at
                        else None,
                        "schema_version": metadata.schema_version,
                    }
                ),
            )

            # TODO: Import evidence items from archive

            return ImportSnapshotResponse(
                investigation_id=new_investigation_id,
                status="imported",
                original_investigation_id=original_id,
                evidence_count=metadata.evidence_count,
                is_replay=True,
            )

    except tarfile.TarError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tar.gz archive: {e}",
        ) from e
