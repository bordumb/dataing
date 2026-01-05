"""Dataset API routes."""

from __future__ import annotations

import os
from typing import Annotated, Any
from uuid import UUID

import structlog
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from dataing.adapters.datasource import SchemaFilter, SourceType, get_registry
from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    verify_api_key,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])

AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]


def _get_encryption_key() -> bytes:
    """Get the encryption key for data source configs."""
    key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        os.environ["ENCRYPTION_KEY"] = key
    return key.encode() if isinstance(key, str) else key


def _decrypt_config(encrypted: str, key: bytes) -> dict[str, Any]:
    """Decrypt configuration."""
    import json

    f = Fernet(key)
    decrypted = f.decrypt(encrypted.encode())
    result: dict[str, Any] = json.loads(decrypted.decode())
    return result


async def _fetch_columns_from_datasource(
    app_db: AppDatabase,
    tenant_id: UUID,
    datasource_id: UUID,
    native_path: str,
) -> list[dict[str, Any]]:
    """Fetch columns for a dataset from its datasource.

    Args:
        app_db: The app database instance.
        tenant_id: The tenant ID.
        datasource_id: The datasource ID.
        native_path: The native path of the table.

    Returns:
        List of column dictionaries with name, data_type, nullable, is_primary_key.
    """
    ds = await app_db.get_data_source(datasource_id, tenant_id)
    if not ds:
        return []

    registry = get_registry()
    try:
        source_type = SourceType(ds["type"])
    except ValueError:
        logger.warning("Unsupported source type for schema fetch", ds_type=ds["type"])
        return []

    if not registry.is_registered(source_type):
        return []

    # Decrypt config
    try:
        encryption_key = _get_encryption_key()
        config = _decrypt_config(ds["connection_config_encrypted"], encryption_key)
    except Exception as e:
        logger.warning("Failed to decrypt datasource config", error=str(e))
        return []

    # Fetch schema and find matching table
    try:
        adapter = registry.create(source_type, config)
        async with adapter:
            schema = await adapter.get_schema(SchemaFilter(max_tables=10000))

        # Search for the table by native_path
        for catalog in schema.catalogs:
            for schema_obj in catalog.schemas:
                for table in schema_obj.tables:
                    if table.native_path == native_path:
                        # Convert columns to response format
                        return [
                            {
                                "name": col.name,
                                "data_type": col.data_type,
                                "nullable": col.nullable,
                                "is_primary_key": col.is_primary_key,
                            }
                            for col in table.columns
                        ]
        return []
    except Exception as e:
        logger.warning(
            "Failed to fetch columns from datasource",
            datasource_id=str(datasource_id),
            native_path=native_path,
            error=str(e),
        )
        return []


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

    # Fetch columns from the datasource
    columns = await _fetch_columns_from_datasource(
        app_db,
        auth.tenant_id,
        UUID(str(ds["datasource_id"])),
        ds["native_path"],
    )

    base = _format_dataset(ds)
    return DatasetDetailResponse(
        **base.model_dump(),
        columns=columns,
    )


@router.get("/{dataset_id}/investigations", response_model=DatasetInvestigationsResponse)
async def get_dataset_investigations(
    dataset_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
    limit: int = Query(default=50, ge=1, le=100),
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
