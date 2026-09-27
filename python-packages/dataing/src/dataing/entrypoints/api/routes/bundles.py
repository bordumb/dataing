"""Context Bundles API endpoints.

This module provides the API for creating and managing context bundles,
which are cacheable snapshots of resolved assets with their context.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from dataing.adapters.db import BundleRepository
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    verify_api_key,
)

router = APIRouter(prefix="/context", tags=["context"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]

# Bundle expiry (default 1 hour)
BUNDLE_EXPIRY_SECONDS = 3600


# --- Request/Response Models ---


class AssetRefRequest(BaseModel):
    """Asset reference in request."""

    platform: str = Field(..., description="Data platform (postgres, snowflake, dbt)")
    name: str = Field(..., description="Fully qualified name (db.schema.table)")
    datasource_id: str | None = Field(
        default=None, description="Optional datasource ID for disambiguation"
    )


class ResolvedAssetResponse(BaseModel):
    """Resolved asset in response."""

    asset: AssetRefRequest
    datasource_id: str | None = None
    dataset_id: str = Field(..., description="Canonical URN")
    dataset_type: str | None = Field(default=None, description="TABLE, VIEW, MODEL, etc.")


class LineageEdge(BaseModel):
    """Lineage edge."""

    source: str
    target: str
    edge_type: str = "transforms"


class BundleLineageGraphResponse(BaseModel):
    """Lineage graph response."""

    root: str | None = None
    datasets: dict[str, dict[str, Any]] = Field(default_factory=dict)
    edges: list[LineageEdge] = Field(default_factory=list)


class OperationalFactsResponse(BaseModel):
    """Operational facts about assets."""

    recent_runs: list[dict[str, Any]] = Field(default_factory=list)
    freshness: dict[str, Any] = Field(default_factory=dict)


class AnomalySummary(BaseModel):
    """Summary of detected anomaly."""

    anomaly_id: str
    dataset_id: str
    anomaly_type: str
    severity: str
    detected_at: datetime


class ContextBundleResponse(BaseModel):
    """Context bundle response."""

    bundle_id: str
    resolved_assets: list[ResolvedAssetResponse]
    default_datasource_id: str | None = None
    lineage: BundleLineageGraphResponse | None = None
    operational: OperationalFactsResponse | None = None
    anomalies: list[AnomalySummary] | None = None
    bundle_hash: str = Field(..., description="Server-derived cache key")
    expires_at: datetime


class AmbiguousAssetCandidate(BaseModel):
    """Candidate when asset is ambiguous."""

    datasource_id: str
    datasource_name: str
    platform: str
    connection_info: str | None = None


class AmbiguousAssetError(BaseModel):
    """Error response for ambiguous asset."""

    asset: AssetRefRequest
    message: str
    candidates: list[AmbiguousAssetCandidate]
    hint: str


class CreateBundleRequest(BaseModel):
    """Request to create a context bundle."""

    assets: list[AssetRefRequest] = Field(
        ..., min_length=1, description="Assets to include in bundle"
    )
    window: str | None = Field(
        default=None, description="Time window for context (e.g., '7d', '24h')"
    )
    include_lineage: bool = Field(default=True, description="Include lineage graph")
    include_operational: bool = Field(default=True, description="Include operational facts")
    include_anomalies: bool = Field(default=True, description="Include anomaly summary")


class AmbiguousAssetsResponse(BaseModel):
    """Response when one or more assets are ambiguous."""

    detail: str = "One or more assets matched multiple datasources"
    ambiguous_assets: list[AmbiguousAssetError]


# --- Helper functions ---


def _compute_bundle_hash(
    assets: list[AssetRefRequest],
    window: str | None,
    resolved_assets: list[ResolvedAssetResponse],
) -> str:
    """Compute deterministic hash for bundle caching.

    Args:
        assets: Original asset references.
        window: Time window.
        resolved_assets: Resolved assets with datasource bindings.

    Returns:
        SHA256 hash string.
    """
    # Create deterministic representation
    data = {
        "assets": [
            {
                "platform": a.platform,
                "name": a.name,
                "datasource_id": a.datasource_id,
            }
            for a in assets
        ],
        "window": window,
        "resolved": [
            {
                "dataset_id": r.dataset_id,
                "datasource_id": r.datasource_id,
            }
            for r in resolved_assets
        ],
    }
    # Sort keys for determinism
    json_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]


async def _resolve_asset(
    asset: AssetRefRequest,
    request: Request,
    auth: ApiKeyContext,
) -> tuple[ResolvedAssetResponse, list[AmbiguousAssetCandidate] | None]:
    """Resolve an asset reference to a concrete datasource.

    Args:
        asset: Asset reference to resolve.
        request: FastAPI request (for app state access).
        auth: Auth context.

    Returns:
        Tuple of (resolved asset, None) on success, or (None, candidates) if ambiguous.
    """
    # Get app database
    app_db = request.app.state.app_db

    # Build URN for lookup
    urn = f"{asset.platform}://{asset.name}"

    # If datasource_id is provided, use it directly
    if asset.datasource_id:
        # Verify the datasource exists and belongs to tenant
        datasource = await app_db.get_datasource(asset.datasource_id, auth.tenant_id)
        if not datasource:
            # Return as resolved anyway - let downstream handle missing datasource
            pass
        return (
            ResolvedAssetResponse(
                asset=asset,
                datasource_id=asset.datasource_id,
                dataset_id=urn,
                dataset_type=None,  # Would be filled by actual resolution
            ),
            None,
        )

    # Search for matching datasources by platform
    matching_datasources = await app_db.find_datasources_by_platform(
        tenant_id=auth.tenant_id,
        platform=asset.platform,
    )

    if len(matching_datasources) == 0:
        # No datasources configured for this platform - still resolve
        return (
            ResolvedAssetResponse(
                asset=asset,
                datasource_id=None,
                dataset_id=urn,
                dataset_type=None,
            ),
            None,
        )
    elif len(matching_datasources) == 1:
        # Exactly one match - use it
        ds = matching_datasources[0]
        return (
            ResolvedAssetResponse(
                asset=asset,
                datasource_id=str(ds["id"]),
                dataset_id=urn,
                dataset_type=None,
            ),
            None,
        )
    else:
        # Ambiguous - multiple datasources match
        candidates = [
            AmbiguousAssetCandidate(
                datasource_id=str(ds["id"]),
                datasource_name=ds["name"],
                platform=ds["platform"],
                connection_info=ds.get("host"),
            )
            for ds in matching_datasources
        ]
        return (None, candidates)  # type: ignore[return-value]


# --- Endpoints ---


@router.post(
    "/bundles",
    response_model=ContextBundleResponse,
    responses={
        409: {
            "description": "Ambiguous assets - multiple datasources match",
            "model": AmbiguousAssetsResponse,
        }
    },
)
async def create_bundle(
    request: Request,
    body: CreateBundleRequest,
    auth: AuthDep,
    response: Response,
) -> ContextBundleResponse:
    """Create a context bundle for the given assets.

    This endpoint resolves asset references to concrete datasources,
    gathers context (lineage, operational facts, anomalies), and returns
    a cacheable bundle.

    If any asset reference is ambiguous (matches multiple datasources),
    returns 409 with candidates and a hint for disambiguation.

    The response includes:
    - bundle_id: Unique identifier for this bundle
    - resolved_assets: Per-asset resolution with datasource binding
    - bundle_hash: Server-computed cache key (also returned as ETag header)
    - Context data (lineage, operational, anomalies) based on request flags
    """
    resolved_assets: list[ResolvedAssetResponse] = []
    ambiguous_errors: list[AmbiguousAssetError] = []

    # Resolve each asset
    for asset in body.assets:
        resolved, candidates = await _resolve_asset(asset, request, auth)
        if candidates is not None:
            ambiguous_errors.append(
                AmbiguousAssetError(
                    asset=asset,
                    message=f"Asset {asset.platform}://{asset.name} matched multiple datasources",
                    candidates=candidates,
                    hint=f"Add datasource_id to the asset reference. "
                    f"Options: {', '.join(c.datasource_id for c in candidates)}",
                )
            )
        else:
            resolved_assets.append(resolved)

    # If any assets are ambiguous, return 409
    if ambiguous_errors:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "One or more assets matched multiple datasources",
                "ambiguous_assets": [e.model_dump() for e in ambiguous_errors],
            },
        )

    # Compute hash for content-addressable deduplication
    bundle_hash = _compute_bundle_hash(body.assets, body.window, resolved_assets)

    # Get default datasource from first resolved asset (if available)
    default_datasource_id = resolved_assets[0].datasource_id if resolved_assets else None

    # Build context data
    lineage_data = BundleLineageGraphResponse() if body.include_lineage else None
    operational_data = OperationalFactsResponse() if body.include_operational else None
    anomalies_data: list[AnomalySummary] | None = [] if body.include_anomalies else None

    # Persist via repository (content-addressable - returns existing if hash matches)
    app_db = request.app.state.app_db
    bundle_repo = BundleRepository(app_db)

    # Convert resolved assets to dict for storage
    assets_for_storage = [
        {
            "asset": {
                "platform": r.asset.platform,
                "name": r.asset.name,
                "datasource_id": r.asset.datasource_id,
            },
            "datasource_id": r.datasource_id,
            "dataset_id": r.dataset_id,
            "dataset_type": r.dataset_type,
        }
        for r in resolved_assets
    ]

    bundle_record = await bundle_repo.create_bundle(
        tenant_id=auth.tenant_id,
        bundle_hash=bundle_hash,
        assets=assets_for_storage,
        window=body.window,
        lineage=lineage_data.model_dump() if lineage_data else None,
        operational=operational_data.model_dump() if operational_data else None,
        anomalies=[a.model_dump() for a in anomalies_data] if anomalies_data else None,
    )

    # Build response from persisted record
    bundle_response = ContextBundleResponse(
        bundle_id=bundle_record["id"],
        resolved_assets=resolved_assets,
        default_datasource_id=default_datasource_id,
        lineage=lineage_data,
        operational=operational_data,
        anomalies=anomalies_data,
        bundle_hash=bundle_hash,
        expires_at=bundle_record["expires_at"],
    )

    # Set ETag header
    response.headers["ETag"] = f'"{bundle_hash}"'

    return bundle_response


@router.get("/bundles/{bundle_id}", response_model=ContextBundleResponse)
async def get_bundle(
    bundle_id: str,
    request: Request,
    auth: AuthDep,
    response: Response,
) -> ContextBundleResponse:
    """Get an existing context bundle by ID.

    Returns the bundle if found and belongs to the authenticated tenant.
    """
    app_db = request.app.state.app_db
    bundle_repo = BundleRepository(app_db)

    try:
        bundle_uuid = UUID(bundle_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid bundle ID: {bundle_id}") from e

    bundle_record = await bundle_repo.get_bundle(bundle_uuid)
    if bundle_record is None:
        raise HTTPException(status_code=404, detail=f"Bundle not found: {bundle_id}")

    # Verify tenant ownership
    if bundle_record["tenant_id"] != str(auth.tenant_id):
        raise HTTPException(status_code=404, detail=f"Bundle not found: {bundle_id}")

    # Reconstruct resolved assets from stored data
    stored_assets = bundle_record.get("assets", [])
    resolved_assets = [
        ResolvedAssetResponse(
            asset=AssetRefRequest(
                platform=a["asset"]["platform"],
                name=a["asset"]["name"],
                datasource_id=a["asset"].get("datasource_id"),
            ),
            datasource_id=a.get("datasource_id"),
            dataset_id=a["dataset_id"],
            dataset_type=a.get("dataset_type"),
        )
        for a in stored_assets
    ]

    # Get default datasource from first asset
    default_datasource_id = resolved_assets[0].datasource_id if resolved_assets else None

    # Reconstruct context data
    lineage_data = None
    if bundle_record.get("lineage"):
        lineage_data = BundleLineageGraphResponse(**bundle_record["lineage"])

    operational_data = None
    if bundle_record.get("operational"):
        operational_data = OperationalFactsResponse(**bundle_record["operational"])

    anomalies_data = None
    if bundle_record.get("anomalies") is not None:
        anomalies_data = [AnomalySummary(**a) for a in bundle_record["anomalies"]]

    # Set ETag header
    response.headers["ETag"] = f'"{bundle_record["bundle_hash"]}"'

    return ContextBundleResponse(
        bundle_id=bundle_record["id"],
        resolved_assets=resolved_assets,
        default_datasource_id=default_datasource_id,
        lineage=lineage_data,
        operational=operational_data,
        anomalies=anomalies_data,
        bundle_hash=bundle_record["bundle_hash"],
        expires_at=bundle_record["expires_at"],
    )


# --- Diff and Explain Request/Response Models ---


class DiffRequest(BaseModel):
    """Request to compute metric diff."""

    bundle_id: str = Field(..., description="Bundle ID to analyze")
    metric: str = Field(..., description="Metric to compare (e.g., row_count, null_rate)")
    window: str = Field(default="7d", description="Time window for comparison (e.g., 7d, 24h)")
    datasource_id: str | None = Field(default=None, description="Optional datasource override")


class DiffSample(BaseModel):
    """Time-series sample for diff."""

    timestamp: datetime
    value: float


class DiffResponse(BaseModel):
    """Response for metric diff."""

    metric: str
    window: str
    current_value: float | None = None
    previous_value: float | None = None
    delta: float | None = None
    delta_percent: float | None = None
    trend: str | None = Field(default=None, description="up, down, stable, or unknown")
    samples: list[DiffSample] = Field(default_factory=list)


class ExplainRequest(BaseModel):
    """Request for AI-powered explanation."""

    bundle_id: str = Field(..., description="Bundle ID to explain")
    focus: str | None = Field(
        default=None,
        description="Focus area (anomalies, lineage, data_quality)",
    )


class ExplainResponse(BaseModel):
    """Response for explanation."""

    summary: str = Field(..., description="Natural language explanation")
    insights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    related_assets: list[str] = Field(default_factory=list)


# --- Diff and Explain Endpoints ---


@router.post("/diff", response_model=DiffResponse)
async def compute_diff(
    body: DiffRequest,
    auth: AuthDep,
) -> DiffResponse:
    """Compute metric difference over a time window.

    Compares the current value of a metric to its historical value
    based on the specified time window.

    Supported metrics:
    - row_count: Number of rows in the dataset
    - null_rate: Percentage of null values
    - distinct_count: Number of distinct values
    - freshness: Time since last update

    Returns the current and previous values, absolute delta,
    percentage change, and trend direction.
    """
    # TODO: Implement actual metric computation
    # For now, return mock data for SDK testing

    # Parse window to determine comparison period
    window = body.window.lower()
    # Convert window to days for mock data calculation
    days = 7  # default
    if window.endswith("d"):
        days = int(window[:-1])
    elif window.endswith("h"):
        days = int(window[:-1]) // 24 or 1  # At least 1 day
    elif window.endswith("w"):
        days = int(window[:-1]) * 7

    # Generate mock samples
    samples: list[DiffSample] = []
    now = datetime.now(UTC)
    for i in range(min(int(days), 30)):
        samples.append(
            DiffSample(
                timestamp=now - timedelta(days=i),
                value=1000.0 + (i * 10),  # Mock increasing values
            )
        )

    # Compute mock values
    current_value = 1000.0
    previous_value = 950.0 if samples else None
    delta = current_value - previous_value if previous_value else None
    delta_percent = (delta / previous_value * 100) if delta and previous_value else None

    # Determine trend
    trend = "unknown"
    if delta:
        if delta > 0:
            trend = "up"
        elif delta < 0:
            trend = "down"
        else:
            trend = "stable"

    return DiffResponse(
        metric=body.metric,
        window=body.window,
        current_value=current_value,
        previous_value=previous_value,
        delta=delta,
        delta_percent=delta_percent,
        trend=trend,
        samples=samples,
    )


@router.post("/explain", response_model=ExplainResponse)
async def explain_context(
    body: ExplainRequest,
    auth: AuthDep,
) -> ExplainResponse:
    """Get an AI-powered explanation of the context bundle.

    Analyzes the assets, lineage, and anomalies in the bundle
    and provides a natural language explanation with insights
    and recommendations.

    Focus areas:
    - anomalies: Focus on detected data quality issues
    - lineage: Focus on data dependencies and flow
    - data_quality: General data quality assessment
    """
    # TODO: Implement actual LLM-powered explanation
    # For now, return mock data for SDK testing

    focus = body.focus or "general"

    # Generate mock explanation based on focus
    if focus == "anomalies":
        summary = (
            "Analysis of the context bundle reveals potential data quality anomalies. "
            "The assets show patterns consistent with data freshness issues and "
            "possible schema drift in upstream dependencies."
        )
        insights = [
            "Detected 3 data freshness anomalies in the last 7 days",
            "Schema changes detected in 2 upstream tables",
            "Volume drop of 15% compared to historical average",
        ]
        recommendations = [
            "Investigate data pipeline for delays",
            "Review recent schema migrations",
            "Set up volume monitoring alerts",
        ]
    elif focus == "lineage":
        summary = (
            "The lineage graph shows a complex data flow with multiple dependencies. "
            "The target assets depend on 5 upstream sources with 3 intermediate transformations."
        )
        insights = [
            "5 upstream data sources identified",
            "3 transformation layers between source and target",
            "2 potential single points of failure in the pipeline",
        ]
        recommendations = [
            "Add redundancy for critical data flows",
            "Document transformation logic",
            "Consider adding data contracts",
        ]
    else:
        summary = (
            "Overall data quality assessment for the context bundle. "
            "The assets are generally healthy with some areas for improvement."
        )
        insights = [
            "Data freshness is within acceptable thresholds",
            "Schema stability is good with minimal drift",
            "Query performance metrics are within normal range",
        ]
        recommendations = [
            "Continue monitoring key metrics",
            "Consider adding data validation rules",
            "Review access patterns for optimization",
        ]

    return ExplainResponse(
        summary=summary,
        insights=insights,
        recommendations=recommendations,
        related_assets=[],  # Would be populated from actual bundle
    )
