"""Lineage API endpoints.

This module provides API endpoints for retrieving data lineage from
various lineage providers (dbt, OpenLineage, Airflow, Dagster, DataHub, etc.).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from dataing.adapters.lineage import (
    DatasetId,
    LineageAdapter,
    get_lineage_registry,
)
from dataing.adapters.lineage.exceptions import (
    ColumnLineageNotSupportedError,
    DatasetNotFoundError,
)
from dataing.entrypoints.api.deps import get_tenant_lineage_adapter
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    verify_api_key,
)

router = APIRouter(prefix="/lineage", tags=["lineage"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]


async def _tenant_lineage_adapter(request: Request, auth: AuthDep) -> LineageAdapter:
    """Get the lineage adapter the caller's organization has configured.

    Provider connection details (manifest paths, API base URLs) come only from
    organization settings, never from the request: a caller-supplied URL or path
    would let any user make the server fetch any URL or read any file it can reach.

    Raises:
        HTTPException: 404 if the organization has no lineage provider configured.
    """
    adapter = await get_tenant_lineage_adapter(request, auth.tenant_id)
    if adapter is None:
        raise HTTPException(
            status_code=404,
            detail="No lineage provider is configured for this organization.",
        )
    return adapter


LineageAdapterDep = Annotated[LineageAdapter, Depends(_tenant_lineage_adapter)]


# --- Request/Response Models ---


class LineageProviderResponse(BaseModel):
    """Response for a lineage provider definition."""

    provider: str
    display_name: str
    description: str
    capabilities: dict[str, Any]
    config_schema: dict[str, Any]


class LineageProvidersResponse(BaseModel):
    """Response for listing lineage providers."""

    providers: list[LineageProviderResponse]


class DatasetResponse(BaseModel):
    """Response for a dataset."""

    id: str
    name: str
    qualified_name: str
    dataset_type: str
    platform: str
    database: str | None = None
    schema_name: str | None = Field(None, alias="schema")
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    owners: list[str] = Field(default_factory=list)
    source_code_url: str | None = None
    source_code_path: str | None = None

    model_config = {"populate_by_name": True}


class LineageEdgeResponse(BaseModel):
    """Response for a lineage edge."""

    source: str
    target: str
    edge_type: str = "transforms"
    job_id: str | None = None


class JobResponse(BaseModel):
    """Response for a job."""

    id: str
    name: str
    job_type: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    source_code_url: str | None = None
    source_code_path: str | None = None


class LineageGraphResponse(BaseModel):
    """Response for a lineage graph."""

    root: str
    datasets: dict[str, DatasetResponse]
    edges: list[LineageEdgeResponse]
    jobs: dict[str, JobResponse]


class UpstreamResponse(BaseModel):
    """Response for upstream datasets."""

    datasets: list[DatasetResponse]
    total: int


class DownstreamResponse(BaseModel):
    """Response for downstream datasets."""

    datasets: list[DatasetResponse]
    total: int


class ColumnLineageResponse(BaseModel):
    """Response for column lineage."""

    target_dataset: str
    target_column: str
    source_dataset: str
    source_column: str
    transformation: str | None = None
    confidence: float = 1.0


class ColumnLineageListResponse(BaseModel):
    """Response for column lineage list."""

    lineage: list[ColumnLineageResponse]


class JobRunResponse(BaseModel):
    """Response for a job run."""

    id: str
    job_id: str
    status: str
    started_at: str
    ended_at: str | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    logs_url: str | None = None


class JobRunsResponse(BaseModel):
    """Response for job runs."""

    runs: list[JobRunResponse]
    total: int


class SearchResultsResponse(BaseModel):
    """Response for dataset search."""

    datasets: list[DatasetResponse]
    total: int


# --- Helper functions ---


def _dataset_to_response(dataset: Any) -> DatasetResponse:
    """Convert Dataset to API response.

    Args:
        dataset: Dataset object.

    Returns:
        DatasetResponse.
    """
    return DatasetResponse(
        id=str(dataset.id),
        name=dataset.name,
        qualified_name=dataset.qualified_name,
        dataset_type=dataset.dataset_type.value,
        platform=dataset.platform,
        database=dataset.database,
        schema_name=dataset.schema,
        description=dataset.description,
        tags=dataset.tags,
        owners=dataset.owners,
        source_code_url=dataset.source_code_url,
        source_code_path=dataset.source_code_path,
    )


def _job_to_response(job: Any) -> JobResponse:
    """Convert Job to API response.

    Args:
        job: Job object.

    Returns:
        JobResponse.
    """
    return JobResponse(
        id=job.id,
        name=job.name,
        job_type=job.job_type.value,
        inputs=[str(i) for i in job.inputs],
        outputs=[str(o) for o in job.outputs],
        source_code_url=job.source_code_url,
        source_code_path=job.source_code_path,
    )


# --- Endpoints ---


@router.get("/providers", response_model=LineageProvidersResponse)
async def list_providers() -> LineageProvidersResponse:
    """List all available lineage providers.

    Returns the configuration schema for each provider, which can be used
    to dynamically generate connection forms in the frontend.
    """
    registry = get_lineage_registry()
    providers = []

    for provider_def in registry.list_providers():
        providers.append(
            LineageProviderResponse(
                provider=provider_def.provider_type.value,
                display_name=provider_def.display_name,
                description=provider_def.description,
                capabilities={
                    "supports_column_lineage": provider_def.capabilities.supports_column_lineage,
                    "supports_job_runs": provider_def.capabilities.supports_job_runs,
                    "supports_freshness": provider_def.capabilities.supports_freshness,
                    "supports_search": provider_def.capabilities.supports_search,
                    "supports_owners": provider_def.capabilities.supports_owners,
                    "supports_tags": provider_def.capabilities.supports_tags,
                    "is_realtime": provider_def.capabilities.is_realtime,
                },
                config_schema=provider_def.config_schema.model_dump(),
            )
        )

    return LineageProvidersResponse(providers=providers)


@router.get("/upstream", response_model=UpstreamResponse)
async def get_upstream(
    adapter: LineageAdapterDep,
    dataset: str = Query(..., description="Dataset identifier (platform://name)"),
    depth: int = Query(1, ge=1, le=10, description="Depth of lineage traversal"),
) -> UpstreamResponse:
    """Get upstream (parent) datasets.

    Returns datasets that feed into the specified dataset.
    """
    dataset_id = DatasetId.from_urn(dataset)

    try:
        upstream = await adapter.get_upstream(dataset_id, depth=depth)
        return UpstreamResponse(
            datasets=[_dataset_to_response(ds) for ds in upstream],
            total=len(upstream),
        )
    except DatasetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/downstream", response_model=DownstreamResponse)
async def get_downstream(
    adapter: LineageAdapterDep,
    dataset: str = Query(..., description="Dataset identifier (platform://name)"),
    depth: int = Query(1, ge=1, le=10, description="Depth of lineage traversal"),
) -> DownstreamResponse:
    """Get downstream (child) datasets.

    Returns datasets that depend on the specified dataset.
    """
    dataset_id = DatasetId.from_urn(dataset)

    try:
        downstream = await adapter.get_downstream(dataset_id, depth=depth)
        return DownstreamResponse(
            datasets=[_dataset_to_response(ds) for ds in downstream],
            total=len(downstream),
        )
    except DatasetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/graph", response_model=LineageGraphResponse)
async def get_lineage_graph(
    adapter: LineageAdapterDep,
    dataset: str = Query(..., description="Dataset identifier (platform://name)"),
    upstream_depth: int = Query(3, ge=0, le=10, description="Upstream traversal depth"),
    downstream_depth: int = Query(3, ge=0, le=10, description="Downstream traversal depth"),
) -> LineageGraphResponse:
    """Get full lineage graph around a dataset.

    Returns a graph structure with datasets, edges, and jobs.
    """
    dataset_id = DatasetId.from_urn(dataset)

    try:
        graph = await adapter.get_lineage_graph(
            dataset_id,
            upstream_depth=upstream_depth,
            downstream_depth=downstream_depth,
        )

        # Convert graph to response format
        datasets_response: dict[str, DatasetResponse] = {}
        for ds_id, ds in graph.datasets.items():
            datasets_response[ds_id] = _dataset_to_response(ds)

        edges_response = [
            LineageEdgeResponse(
                source=str(e.source),
                target=str(e.target),
                edge_type=e.edge_type,
                job_id=e.job.id if e.job else None,
            )
            for e in graph.edges
        ]

        jobs_response: dict[str, JobResponse] = {}
        for job_id, job in graph.jobs.items():
            jobs_response[job_id] = _job_to_response(job)

        return LineageGraphResponse(
            root=str(graph.root),
            datasets=datasets_response,
            edges=edges_response,
            jobs=jobs_response,
        )
    except DatasetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/column-lineage", response_model=ColumnLineageListResponse)
async def get_column_lineage(
    adapter: LineageAdapterDep,
    dataset: str = Query(..., description="Dataset identifier (platform://name)"),
    column: str = Query(..., description="Column name to trace"),
) -> ColumnLineageListResponse:
    """Get column-level lineage.

    Returns the source columns that feed into the specified column.
    Not all providers support column lineage.
    """
    dataset_id = DatasetId.from_urn(dataset)

    try:
        lineage = await adapter.get_column_lineage(dataset_id, column)
        return ColumnLineageListResponse(
            lineage=[
                ColumnLineageResponse(
                    target_dataset=str(cl.target_dataset),
                    target_column=cl.target_column,
                    source_dataset=str(cl.source_dataset),
                    source_column=cl.source_column,
                    transformation=cl.transformation,
                    confidence=cl.confidence,
                )
                for cl in lineage
            ]
        )
    except ColumnLineageNotSupportedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DatasetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/job/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    auth: AuthDep,
) -> JobResponse:
    """Get job details.

    Returns information about a job that produces or consumes datasets.
    """
    # For now, we need to search for the job
    # This is a simplified implementation
    raise HTTPException(
        status_code=501,
        detail="Job lookup by ID not yet implemented. Use dataset endpoints.",
    )


@router.get("/job/{job_id}/runs", response_model=JobRunsResponse)
async def get_job_runs(
    job_id: str,
    adapter: LineageAdapterDep,
    limit: int = Query(10, ge=1, le=100, description="Maximum runs to return"),
) -> JobRunsResponse:
    """Get recent runs of a job.

    Returns execution history for the specified job.
    """
    try:
        runs = await adapter.get_recent_runs(job_id, limit=limit)
        return JobRunsResponse(
            runs=[
                JobRunResponse(
                    id=r.id,
                    job_id=r.job_id,
                    status=r.status.value,
                    started_at=r.started_at.isoformat(),
                    ended_at=r.ended_at.isoformat() if r.ended_at else None,
                    duration_seconds=r.duration_seconds,
                    error_message=r.error_message,
                    logs_url=r.logs_url,
                )
                for r in runs
            ],
            total=len(runs),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/search", response_model=SearchResultsResponse)
async def search_datasets(
    adapter: LineageAdapterDep,
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
) -> SearchResultsResponse:
    """Search for datasets by name or description.

    Returns datasets matching the search query.
    """
    try:
        datasets = await adapter.search_datasets(q, limit=limit)
        return SearchResultsResponse(
            datasets=[_dataset_to_response(ds) for ds in datasets],
            total=len(datasets),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/datasets", response_model=SearchResultsResponse)
async def list_datasets(
    adapter: LineageAdapterDep,
    platform: str | None = Query(None, description="Filter by platform"),
    database: str | None = Query(None, description="Filter by database"),
    schema_name: str | None = Query(None, alias="schema", description="Filter by schema"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
) -> SearchResultsResponse:
    """List datasets with optional filters.

    Returns datasets from the lineage provider.
    """
    try:
        datasets = await adapter.list_datasets(
            platform=platform,
            database=database,
            schema=schema_name,
            limit=limit,
        )
        return SearchResultsResponse(
            datasets=[_dataset_to_response(ds) for ds in datasets],
            total=len(datasets),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/dataset/{dataset_id:path}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: str,
    adapter: LineageAdapterDep,
) -> DatasetResponse:
    """Get dataset details.

    Returns metadata for a specific dataset.
    """
    ds_id = DatasetId.from_urn(dataset_id)

    try:
        dataset = await adapter.get_dataset(ds_id)
        if not dataset:
            raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")
        return _dataset_to_response(dataset)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
