"""Dataset API routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    verify_api_key,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])

AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]


class DatasetResponse(BaseModel):
    """Response for a dataset."""

    id: str
    datasource_id: str
    datasource_name: str | None = None
    datasource_type: str | None = None
    native_path: str
    name: str
    table_type: str
    schema_name: str | None = None
    catalog_name: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    last_synced_at: str | None = None
    created_at: str


class DatasetListResponse(BaseModel):
    """Response for listing datasets."""

    datasets: list[DatasetResponse]
    total: int


class DatasetDetailResponse(DatasetResponse):
    """Detailed dataset response with columns."""

    columns: list[dict[str, Any]] = Field(default_factory=list)


class InvestigationSummary(BaseModel):
    """Summary of an investigation for dataset detail."""

    id: str
    dataset_id: str
    metric_name: str
    status: str
    severity: str | None = None
    created_at: str
    completed_at: str | None = None


class DatasetInvestigationsResponse(BaseModel):
    """Response for dataset investigations."""

    investigations: list[InvestigationSummary]
    total: int


def _format_dataset(ds: dict[str, Any]) -> DatasetResponse:
    """Format dataset record for response."""
    return DatasetResponse(
        id=str(ds["id"]),
        datasource_id=str(ds["datasource_id"]),
        datasource_name=ds.get("datasource_name"),
        datasource_type=ds.get("datasource_type"),
        native_path=ds["native_path"],
        name=ds["name"],
        table_type=ds["table_type"],
        schema_name=ds.get("schema_name"),
        catalog_name=ds.get("catalog_name"),
        row_count=ds.get("row_count"),
        column_count=ds.get("column_count"),
        last_synced_at=(ds["last_synced_at"].isoformat() if ds.get("last_synced_at") else None),
        created_at=ds["created_at"].isoformat(),
    )


@router.get("/{dataset_id}", response_model=DatasetDetailResponse)
async def get_dataset(
    dataset_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> DatasetDetailResponse:
    """Get a dataset by ID with column information."""
    ds = await app_db.get_dataset_by_id(auth.tenant_id, dataset_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    base = _format_dataset(ds)
    return DatasetDetailResponse(
        **base.model_dump(),
        columns=[],  # Columns fetched separately via schema endpoint
    )


@router.get("/{dataset_id}/investigations", response_model=DatasetInvestigationsResponse)
async def get_dataset_investigations(
    dataset_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
    limit: int = 50,
) -> DatasetInvestigationsResponse:
    """Get investigations for a dataset."""
    ds = await app_db.get_dataset_by_id(auth.tenant_id, dataset_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    investigations = await app_db.list_investigations_for_dataset(
        auth.tenant_id,
        ds["native_path"],
        limit=limit,
    )

    summaries = [
        InvestigationSummary(
            id=str(inv["id"]),
            dataset_id=inv["dataset_id"],
            metric_name=inv["metric_name"],
            status=inv["status"],
            severity=inv.get("severity"),
            created_at=inv["created_at"].isoformat(),
            completed_at=(inv["completed_at"].isoformat() if inv.get("completed_at") else None),
        )
        for inv in investigations
    ]

    return DatasetInvestigationsResponse(
        investigations=summaries,
        total=len(summaries),
    )
