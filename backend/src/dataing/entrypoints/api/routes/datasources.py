"""Data source management routes using the new unified adapter architecture.

This module provides API endpoints for managing data sources using the
pluggable adapter architecture defined in the data_context specification.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from dataing.adapters.datasource import (
    SchemaFilter,
    SourceType,
    get_registry,
)
from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    require_scope,
    verify_api_key,
)

router = APIRouter(prefix="/datasources", tags=["datasources"])

# Annotated types for dependency injection
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]


def get_encryption_key() -> bytes:
    """Get the encryption key for data source configs.

    Checks DATADR_ENCRYPTION_KEY first (used by demo), then ENCRYPTION_KEY.
    """
    key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        os.environ["ENCRYPTION_KEY"] = key
    return key.encode() if isinstance(key, str) else key


# Request/Response Models


class CreateDataSourceRequest(BaseModel):
    """Request to create a new data source."""

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., description="Source type (e.g., 'postgresql', 'mongodb')")
    config: dict[str, Any] = Field(..., description="Configuration for the adapter")
    is_default: bool = False


class UpdateDataSourceRequest(BaseModel):
    """Request to update a data source."""

    name: str | None = Field(None, min_length=1, max_length=100)
    config: dict[str, Any] | None = None
    is_default: bool | None = None


class DataSourceResponse(BaseModel):
    """Response for a data source."""

    id: str
    name: str
    type: str
    category: str
    is_default: bool
    is_active: bool
    status: str
    last_health_check_at: datetime | None = None
    created_at: datetime


class DataSourceListResponse(BaseModel):
    """Response for listing data sources."""

    data_sources: list[DataSourceResponse]
    total: int


class TestConnectionRequest(BaseModel):
    """Request to test a connection."""

    type: str
    config: dict[str, Any]


class TestConnectionResponse(BaseModel):
    """Response for testing a connection."""

    success: bool
    message: str
    latency_ms: int | None = None
    server_version: str | None = None


class SourceTypeResponse(BaseModel):
    """Response for a source type definition."""

    type: str
    display_name: str
    category: str
    icon: str
    description: str
    capabilities: dict[str, Any]
    config_schema: dict[str, Any]


class SourceTypesResponse(BaseModel):
    """Response for listing source types."""

    types: list[SourceTypeResponse]


class SchemaTableResponse(BaseModel):
    """Response for a table in the schema."""

    name: str
    table_type: str
    native_type: str
    native_path: str
    columns: list[dict[str, Any]]
    row_count: int | None = None
    size_bytes: int | None = None


class SchemaResponseModel(BaseModel):
    """Response for schema discovery."""

    source_id: str
    source_type: str
    source_category: str
    fetched_at: datetime
    catalogs: list[dict[str, Any]]


class QueryRequest(BaseModel):
    """Request to execute a query."""

    query: str
    timeout_seconds: int = 30


class QueryResponse(BaseModel):
    """Response for query execution."""

    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = False
    execution_time_ms: int | None = None


class StatsRequest(BaseModel):
    """Request for column statistics."""

    table: str
    columns: list[str]


class StatsResponse(BaseModel):
    """Response for column statistics."""

    table: str
    row_count: int | None = None
    columns: dict[str, dict[str, Any]]


class SyncResponse(BaseModel):
    """Response for schema sync."""

    datasets_synced: int
    datasets_removed: int
    message: str


class DatasetSummary(BaseModel):
    """Summary of a dataset for list responses."""

    id: str
    datasource_id: str
    native_path: str
    name: str
    table_type: str
    schema_name: str | None = None
    catalog_name: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    last_synced_at: str | None = None
    created_at: str


class DatasourceDatasetsResponse(BaseModel):
    """Response for listing datasets of a datasource."""

    datasets: list[DatasetSummary]
    total: int


def _encrypt_config(config: dict[str, Any], key: bytes) -> str:
    """Encrypt configuration."""
    f = Fernet(key)
    encrypted = f.encrypt(json.dumps(config).encode())
    return encrypted.decode()


def _decrypt_config(encrypted: str, key: bytes) -> dict[str, Any]:
    """Decrypt configuration."""
    f = Fernet(key)
    decrypted = f.decrypt(encrypted.encode())
    result: dict[str, Any] = json.loads(decrypted.decode())
    return result


@router.get("/types", response_model=SourceTypesResponse)
async def list_source_types() -> SourceTypesResponse:
    """List all supported data source types.

    Returns the configuration schema for each type, which can be used
    to dynamically generate connection forms in the frontend.
    """
    registry = get_registry()
    types_list = []

    for type_def in registry.list_types():
        types_list.append(
            SourceTypeResponse(
                type=type_def.type.value,
                display_name=type_def.display_name,
                category=type_def.category.value,
                icon=type_def.icon,
                description=type_def.description,
                capabilities=type_def.capabilities.model_dump(),
                config_schema=type_def.config_schema.model_dump(),
            )
        )

    return SourceTypesResponse(types=types_list)


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(
    request: TestConnectionRequest,
) -> TestConnectionResponse:
    """Test a connection without saving it.

    Use this endpoint to validate connection settings before creating
    a data source.
    """
    registry = get_registry()

    try:
        source_type = SourceType(request.type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {request.type}",
        ) from None

    if not registry.is_registered(source_type):
        raise HTTPException(
            status_code=400,
            detail=f"Source type not available: {request.type}",
        )

    try:
        adapter = registry.create(source_type, request.config)
        async with adapter:
            result = await adapter.test_connection()

        return TestConnectionResponse(
            success=result.success,
            message=result.message,
            latency_ms=result.latency_ms,
            server_version=result.server_version,
        )
    except Exception as e:
        return TestConnectionResponse(
            success=False,
            message=str(e),
        )


@router.post("/", response_model=DataSourceResponse, status_code=201)
async def create_datasource(
    request: CreateDataSourceRequest,
    auth: WriteScopeDep,
    app_db: AppDbDep,
) -> DataSourceResponse:
    """Create a new data source.

    Tests the connection before saving. Returns 400 if connection test fails.
    """
    registry = get_registry()

    try:
        source_type = SourceType(request.type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {request.type}",
        ) from None

    if not registry.is_registered(source_type):
        raise HTTPException(
            status_code=400,
            detail=f"Source type not available: {request.type}",
        )

    # Test connection first
    try:
        adapter = registry.create(source_type, request.config)
        async with adapter:
            result = await adapter.test_connection()
            if not result.success:
                raise HTTPException(status_code=400, detail=result.message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}") from e

    # Get type definition for category
    type_def = registry.get_definition(source_type)
    category = type_def.category.value if type_def else "database"

    # Encrypt config
    encryption_key = get_encryption_key()
    encrypted_config = _encrypt_config(request.config, encryption_key)

    # Save to database
    db_result = await app_db.create_data_source(
        tenant_id=auth.tenant_id,
        name=request.name,
        type=request.type,
        connection_config_encrypted=encrypted_config,
        is_default=request.is_default,
    )

    # Update health check status
    await app_db.update_data_source_health(db_result["id"], "healthy")

    return DataSourceResponse(
        id=str(db_result["id"]),
        name=db_result["name"],
        type=db_result["type"],
        category=category,
        is_default=db_result["is_default"],
        is_active=db_result["is_active"],
        status="connected",
        last_health_check_at=datetime.now(),
        created_at=db_result["created_at"],
    )


@router.get("/", response_model=DataSourceListResponse)
async def list_datasources(
    auth: AuthDep,
    app_db: AppDbDep,
) -> DataSourceListResponse:
    """List all data sources for the current tenant."""
    data_sources = await app_db.list_data_sources(auth.tenant_id)
    registry = get_registry()

    responses = []
    for ds in data_sources:
        # Get category from registry
        try:
            source_type = SourceType(ds["type"])
            type_def = registry.get_definition(source_type)
            category = type_def.category.value if type_def else "database"
        except ValueError:
            category = "database"

        status = ds.get("last_health_check_status", "unknown")
        if status == "healthy":
            status = "connected"
        elif status == "unhealthy":
            status = "error"
        else:
            status = "disconnected"

        responses.append(
            DataSourceResponse(
                id=str(ds["id"]),
                name=ds["name"],
                type=ds["type"],
                category=category,
                is_default=ds["is_default"],
                is_active=ds["is_active"],
                status=status,
                last_health_check_at=ds.get("last_health_check_at"),
                created_at=ds["created_at"],
            )
        )

    return DataSourceListResponse(
        data_sources=responses,
        total=len(responses),
    )


@router.get("/{datasource_id}", response_model=DataSourceResponse)
async def get_datasource(
    datasource_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> DataSourceResponse:
    """Get a specific data source."""
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    registry = get_registry()
    try:
        source_type = SourceType(ds["type"])
        type_def = registry.get_definition(source_type)
        category = type_def.category.value if type_def else "database"
    except ValueError:
        category = "database"

    status = ds.get("last_health_check_status", "unknown")
    if status == "healthy":
        status = "connected"
    elif status == "unhealthy":
        status = "error"
    else:
        status = "disconnected"

    return DataSourceResponse(
        id=str(ds["id"]),
        name=ds["name"],
        type=ds["type"],
        category=category,
        is_default=ds["is_default"],
        is_active=ds["is_active"],
        status=status,
        last_health_check_at=ds.get("last_health_check_at"),
        created_at=ds["created_at"],
    )


@router.delete("/{datasource_id}", status_code=204, response_class=Response)
async def delete_datasource(
    datasource_id: UUID,
    auth: WriteScopeDep,
    app_db: AppDbDep,
) -> Response:
    """Delete a data source (soft delete)."""
    success = await app_db.delete_data_source(datasource_id, auth.tenant_id)

    if not success:
        raise HTTPException(status_code=404, detail="Data source not found")

    return Response(status_code=204)


@router.post("/{datasource_id}/test", response_model=TestConnectionResponse)
async def test_datasource_connection(
    datasource_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> TestConnectionResponse:
    """Test connectivity for an existing data source."""
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    registry = get_registry()

    try:
        source_type = SourceType(ds["type"])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {ds['type']}",
        ) from None

    if not registry.is_registered(source_type):
        raise HTTPException(
            status_code=400,
            detail=f"Source type not available: {ds['type']}",
        )

    # Decrypt config
    encryption_key = get_encryption_key()
    try:
        config = _decrypt_config(ds["connection_config_encrypted"], encryption_key)
    except Exception as e:
        return TestConnectionResponse(
            success=False,
            message=f"Failed to decrypt configuration: {str(e)}",
        )

    # Test connection
    try:
        adapter = registry.create(source_type, config)
        async with adapter:
            result = await adapter.test_connection()

        # Update health check status
        status = "healthy" if result.success else "unhealthy"
        await app_db.update_data_source_health(datasource_id, status)

        return TestConnectionResponse(
            success=result.success,
            message=result.message,
            latency_ms=result.latency_ms,
            server_version=result.server_version,
        )
    except Exception as e:
        await app_db.update_data_source_health(datasource_id, "unhealthy")
        return TestConnectionResponse(
            success=False,
            message=str(e),
        )


@router.get("/{datasource_id}/schema", response_model=SchemaResponseModel)
async def get_datasource_schema(
    datasource_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
    table_pattern: str | None = None,
    include_views: bool = True,
    max_tables: int = 1000,
) -> SchemaResponseModel:
    """Get schema from a data source.

    Returns unified schema with catalogs, schemas, and tables.
    """
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    registry = get_registry()

    try:
        source_type = SourceType(ds["type"])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {ds['type']}",
        ) from None

    if not registry.is_registered(source_type):
        raise HTTPException(
            status_code=400,
            detail=f"Source type not available: {ds['type']}",
        )

    # Decrypt config
    encryption_key = get_encryption_key()
    try:
        config = _decrypt_config(ds["connection_config_encrypted"], encryption_key)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to decrypt configuration: {str(e)}",
        ) from e

    # Build filter
    schema_filter = SchemaFilter(
        table_pattern=table_pattern,
        include_views=include_views,
        max_tables=max_tables,
    )

    # Get schema
    try:
        adapter = registry.create(source_type, config)
        async with adapter:
            schema = await adapter.get_schema(schema_filter)

        return SchemaResponseModel(
            source_id=str(datasource_id),
            source_type=schema.source_type.value,
            source_category=schema.source_category.value,
            fetched_at=schema.fetched_at,
            catalogs=[cat.model_dump() for cat in schema.catalogs],
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch schema: {str(e)}",
        ) from e


@router.post("/{datasource_id}/query", response_model=QueryResponse)
async def execute_query(
    datasource_id: UUID,
    request: QueryRequest,
    auth: AuthDep,
    app_db: AppDbDep,
) -> QueryResponse:
    """Execute a query against a data source.

    Only works for sources that support SQL or similar query languages.
    """
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    registry = get_registry()

    try:
        source_type = SourceType(ds["type"])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {ds['type']}",
        ) from None

    type_def = registry.get_definition(source_type)
    if not type_def or not type_def.capabilities.supports_sql:
        raise HTTPException(
            status_code=400,
            detail=f"Source type {ds['type']} does not support SQL queries",
        )

    # Decrypt config
    encryption_key = get_encryption_key()
    try:
        config = _decrypt_config(ds["connection_config_encrypted"], encryption_key)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to decrypt configuration: {str(e)}",
        ) from e

    # Execute query
    try:
        adapter = registry.create(source_type, config)
        async with adapter:
            # Check if adapter has execute_query method
            if not hasattr(adapter, "execute_query"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Source type {ds['type']} does not support query execution",
                )
            result = await adapter.execute_query(
                request.query,
                timeout_seconds=request.timeout_seconds,
            )

        return QueryResponse(
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
            truncated=result.truncated,
            execution_time_ms=result.execution_time_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Query execution failed: {str(e)}",
        ) from e


@router.post("/{datasource_id}/stats", response_model=StatsResponse)
async def get_column_stats(
    datasource_id: UUID,
    request: StatsRequest,
    auth: AuthDep,
    app_db: AppDbDep,
) -> StatsResponse:
    """Get statistics for columns in a table.

    Only works for sources that support column statistics.
    """
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    registry = get_registry()

    try:
        source_type = SourceType(ds["type"])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {ds['type']}",
        ) from None

    type_def = registry.get_definition(source_type)
    if not type_def or not type_def.capabilities.supports_column_stats:
        raise HTTPException(
            status_code=400,
            detail=f"Source type {ds['type']} does not support column statistics",
        )

    # Decrypt config
    encryption_key = get_encryption_key()
    try:
        config = _decrypt_config(ds["connection_config_encrypted"], encryption_key)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to decrypt configuration: {str(e)}",
        ) from e

    # Get stats
    try:
        adapter = registry.create(source_type, config)
        async with adapter:
            # Check if adapter has get_column_stats method
            if not hasattr(adapter, "get_column_stats"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Source type {ds['type']} does not support column statistics",
                )

            # Parse table name
            parts = request.table.split(".")
            if len(parts) == 2:
                schema, table = parts
            else:
                schema = None
                table = request.table

            stats = await adapter.get_column_stats(table, request.columns, schema)

            # Try to get row count
            row_count = None
            if hasattr(adapter, "count_rows"):
                row_count = await adapter.count_rows(table, schema)

        return StatsResponse(
            table=request.table,
            row_count=row_count,
            columns=stats,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get column statistics: {str(e)}",
        ) from e


@router.post("/{datasource_id}/sync", response_model=SyncResponse)
async def sync_datasource_schema(
    datasource_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> SyncResponse:
    """Sync schema and register/update datasets.

    Discovers all tables from the data source and upserts them
    into the datasets table. Soft-deletes datasets that no longer exist.
    """
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    registry = get_registry()

    try:
        source_type = SourceType(ds["type"])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {ds['type']}",
        ) from None

    # Decrypt config
    encryption_key = get_encryption_key()
    try:
        config = _decrypt_config(ds["connection_config_encrypted"], encryption_key)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to decrypt configuration: {e!s}",
        ) from e

    # Get schema
    try:
        adapter = registry.create(source_type, config)
        async with adapter:
            schema = await adapter.get_schema(SchemaFilter(max_tables=10000))

        # Build dataset records from schema
        dataset_records: list[dict[str, Any]] = []
        for catalog in schema.catalogs:
            for schema_obj in catalog.schemas:
                for table in schema_obj.tables:
                    dataset_records.append(
                        {
                            "native_path": table.native_path,
                            "name": table.name,
                            "table_type": table.table_type,
                            "schema_name": schema_obj.name,
                            "catalog_name": catalog.name,
                            "row_count": table.row_count,
                            "column_count": len(table.columns),
                        }
                    )

        # Upsert datasets
        synced_count = await app_db.upsert_datasets(
            auth.tenant_id,
            datasource_id,
            dataset_records,
        )

        # Soft-delete removed datasets
        active_paths = {d["native_path"] for d in dataset_records}
        removed_count = await app_db.deactivate_stale_datasets(
            auth.tenant_id,
            datasource_id,
            active_paths,
        )

        return SyncResponse(
            datasets_synced=synced_count,
            datasets_removed=removed_count,
            message=f"Synced {synced_count} datasets, removed {removed_count}",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Schema sync failed: {e!s}",
        ) from e


@router.get("/{datasource_id}/datasets", response_model=DatasourceDatasetsResponse)
async def list_datasource_datasets(
    datasource_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
    table_type: str | None = None,
    search: str | None = None,
    limit: int = Query(default=1000, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
) -> DatasourceDatasetsResponse:
    """List datasets for a datasource."""
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    datasets = await app_db.list_datasets(
        auth.tenant_id,
        datasource_id,
        table_type=table_type,
        search=search,
        limit=limit,
        offset=offset,
    )

    total = await app_db.get_dataset_count(
        auth.tenant_id,
        datasource_id,
        table_type=table_type,
        search=search,
    )

    return DatasourceDatasetsResponse(
        datasets=[
            DatasetSummary(
                id=str(d["id"]),
                datasource_id=str(d["datasource_id"]),
                native_path=d["native_path"],
                name=d["name"],
                table_type=d["table_type"],
                schema_name=d.get("schema_name"),
                catalog_name=d.get("catalog_name"),
                row_count=d.get("row_count"),
                column_count=d.get("column_count"),
                last_synced_at=(
                    d["last_synced_at"].isoformat() if d.get("last_synced_at") else None
                ),
                created_at=d["created_at"].isoformat(),
            )
            for d in datasets
        ],
        total=total,
    )
