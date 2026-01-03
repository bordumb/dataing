"""Data source management routes."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.postgres import PostgresAdapter
from dataing.adapters.db.trino import TrinoAdapter
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing.models.data_source import DataSourceType

router = APIRouter(prefix="/datasources", tags=["datasources"])


def get_encryption_key() -> bytes:
    """Get the encryption key for data source configs.

    Returns:
        Encryption key as bytes.

    Raises:
        RuntimeError: If ENCRYPTION_KEY is not set.
    """
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        # For development, use a default key (NOT FOR PRODUCTION)
        key = Fernet.generate_key().decode()
        os.environ["ENCRYPTION_KEY"] = key
    return key.encode() if isinstance(key, str) else key


class ConnectionConfig(BaseModel):
    """Database connection configuration."""

    host: str
    port: int = 5432
    database: str
    username: str
    password: str
    ssl_mode: str = "prefer"


class CreateDataSourceRequest(BaseModel):
    """Request to create a new data source."""

    name: str = Field(..., min_length=1, max_length=100)
    type: DataSourceType
    connection_config: ConnectionConfig
    is_default: bool = False


class UpdateDataSourceRequest(BaseModel):
    """Request to update a data source."""

    name: str | None = Field(None, min_length=1, max_length=100)
    connection_config: ConnectionConfig | None = None
    is_default: bool | None = None


class DataSourceResponse(BaseModel):
    """Response for a data source."""

    id: str
    name: str
    type: str
    is_default: bool
    is_active: bool
    last_health_check_at: datetime | None = None
    last_health_check_status: str | None = None
    created_at: datetime


class DataSourceListResponse(BaseModel):
    """Response for listing data sources."""

    data_sources: list[DataSourceResponse]
    total: int


class TestConnectionResponse(BaseModel):
    """Response for testing a connection."""

    success: bool
    message: str
    tables_found: int | None = None


class SchemaResponse(BaseModel):
    """Response for schema discovery."""

    tables: list[dict[str, Any]]


def _build_connection_string(config: ConnectionConfig, ds_type: DataSourceType) -> str:
    """Build a connection string from config."""
    if ds_type == DataSourceType.POSTGRES:
        ssl_suffix = f"?sslmode={config.ssl_mode}" if config.ssl_mode else ""
        return f"postgresql://{config.username}:{config.password}@{config.host}:{config.port}/{config.database}{ssl_suffix}"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Data source type '{ds_type}' is not yet supported for connection strings",
        )


def _create_adapter(config: ConnectionConfig, ds_type: DataSourceType) -> PostgresAdapter | TrinoAdapter:
    """Create a database adapter from config."""
    if ds_type == DataSourceType.POSTGRES:
        connection_string = _build_connection_string(config, ds_type)
        return PostgresAdapter(connection_string)
    elif ds_type == DataSourceType.TRINO:
        # Parse database as catalog.schema for Trino
        parts = config.database.split(".")
        if len(parts) == 2:
            catalog, schema = parts
        else:
            catalog = config.database
            schema = "default"
        return TrinoAdapter(
            host=config.host,
            port=config.port,
            catalog=catalog,
            schema=schema,
            user=config.username,
        )
    else:
        raise ValueError(f"Data source type '{ds_type}' is not yet supported")


async def _test_connection(config: ConnectionConfig, ds_type: DataSourceType) -> tuple[bool, str, int]:
    """Test a database connection.

    Returns:
        Tuple of (success, message, table_count)
    """
    try:
        if ds_type in (DataSourceType.POSTGRES, DataSourceType.TRINO):
            adapter = _create_adapter(config, ds_type)
            await adapter.connect()
            try:
                schema = await adapter.get_schema()
                return True, "Connection successful", len(schema.tables)
            finally:
                await adapter.close()
        else:
            return False, f"Data source type '{ds_type}' is not yet supported", 0
    except Exception as e:
        return False, f"Connection failed: {str(e)}", 0


def _encrypt_config(config: ConnectionConfig, key: bytes) -> str:
    """Encrypt connection configuration."""
    import json

    f = Fernet(key)
    encrypted = f.encrypt(json.dumps(config.model_dump()).encode())
    return encrypted.decode()


def _decrypt_config(encrypted: str, key: bytes) -> ConnectionConfig:
    """Decrypt connection configuration."""
    import json

    f = Fernet(key)
    decrypted = f.decrypt(encrypted.encode())
    return ConnectionConfig(**json.loads(decrypted.decode()))


@router.post("/", response_model=DataSourceResponse, status_code=201)
async def create_datasource(
    request: CreateDataSourceRequest,
    auth: ApiKeyContext = Depends(require_scope("write")),
    app_db: AppDatabase = Depends(get_app_db),
) -> DataSourceResponse:
    """Create a new data source connection.

    Tests the connection before saving. Returns 400 if connection test fails.
    """
    # Test connection first
    success, message, tables = await _test_connection(request.connection_config, request.type)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Encrypt connection config
    encryption_key = get_encryption_key()
    encrypted_config = _encrypt_config(request.connection_config, encryption_key)

    # Save to database
    result = await app_db.create_data_source(
        tenant_id=auth.tenant_id,
        name=request.name,
        type=request.type.value,
        connection_config_encrypted=encrypted_config,
        is_default=request.is_default,
    )

    # Update health check status
    await app_db.update_data_source_health(result["id"], "healthy")

    return DataSourceResponse(
        id=str(result["id"]),
        name=result["name"],
        type=result["type"],
        is_default=result["is_default"],
        is_active=result["is_active"],
        last_health_check_at=datetime.now(),
        last_health_check_status="healthy",
        created_at=result["created_at"],
    )


@router.get("/", response_model=DataSourceListResponse)
async def list_datasources(
    auth: ApiKeyContext = Depends(verify_api_key),
    app_db: AppDatabase = Depends(get_app_db),
) -> DataSourceListResponse:
    """List all data sources for the current tenant."""
    data_sources = await app_db.list_data_sources(auth.tenant_id)

    return DataSourceListResponse(
        data_sources=[
            DataSourceResponse(
                id=str(ds["id"]),
                name=ds["name"],
                type=ds["type"],
                is_default=ds["is_default"],
                is_active=ds["is_active"],
                last_health_check_at=ds.get("last_health_check_at"),
                last_health_check_status=ds.get("last_health_check_status"),
                created_at=ds["created_at"],
            )
            for ds in data_sources
        ],
        total=len(data_sources),
    )


@router.get("/{datasource_id}", response_model=DataSourceResponse)
async def get_datasource(
    datasource_id: UUID,
    auth: ApiKeyContext = Depends(verify_api_key),
    app_db: AppDatabase = Depends(get_app_db),
) -> DataSourceResponse:
    """Get a specific data source."""
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    return DataSourceResponse(
        id=str(ds["id"]),
        name=ds["name"],
        type=ds["type"],
        is_default=ds["is_default"],
        is_active=ds["is_active"],
        last_health_check_at=ds.get("last_health_check_at"),
        last_health_check_status=ds.get("last_health_check_status"),
        created_at=ds["created_at"],
    )


@router.delete("/{datasource_id}", status_code=204, response_class=Response)
async def delete_datasource(
    datasource_id: UUID,
    auth: ApiKeyContext = Depends(require_scope("write")),
    app_db: AppDatabase = Depends(get_app_db),
) -> Response:
    """Delete a data source (soft delete)."""
    success = await app_db.delete_data_source(datasource_id, auth.tenant_id)

    if not success:
        raise HTTPException(status_code=404, detail="Data source not found")

    return Response(status_code=204)


@router.post("/{datasource_id}/test", response_model=TestConnectionResponse)
async def test_datasource(
    datasource_id: UUID,
    auth: ApiKeyContext = Depends(verify_api_key),
    app_db: AppDatabase = Depends(get_app_db),
) -> TestConnectionResponse:
    """Test data source connectivity."""
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    # Decrypt connection config
    encryption_key = get_encryption_key()
    try:
        config = _decrypt_config(ds["connection_config_encrypted"], encryption_key)
    except Exception as e:
        return TestConnectionResponse(
            success=False,
            message=f"Failed to decrypt connection config: {str(e)}",
        )

    # Test connection
    ds_type = DataSourceType(ds["type"])
    success, message, tables = await _test_connection(config, ds_type)

    # Update health check status
    status = "healthy" if success else "unhealthy"
    await app_db.update_data_source_health(datasource_id, status)

    return TestConnectionResponse(
        success=success,
        message=message,
        tables_found=tables if success else None,
    )


@router.get("/{datasource_id}/schema", response_model=SchemaResponse)
async def get_schema(
    datasource_id: UUID,
    table_pattern: str | None = None,
    auth: ApiKeyContext = Depends(verify_api_key),
    app_db: AppDatabase = Depends(get_app_db),
) -> SchemaResponse:
    """Get schema from data source.

    Args:
        datasource_id: The data source ID.
        table_pattern: Optional pattern to filter tables.
    """
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    # Decrypt connection config
    encryption_key = get_encryption_key()
    try:
        config = _decrypt_config(ds["connection_config_encrypted"], encryption_key)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to decrypt connection config: {str(e)}",
        )

    ds_type = DataSourceType(ds["type"])

    try:
        if ds_type in (DataSourceType.POSTGRES, DataSourceType.TRINO):
            adapter = _create_adapter(config, ds_type)
            await adapter.connect()
            try:
                schema = await adapter.get_schema(table_pattern)
                return SchemaResponse(
                    tables=[
                        {
                            "table_name": t.table_name,
                            "columns": list(t.columns),
                            "column_types": t.column_types,
                        }
                        for t in schema.tables
                    ]
                )
            finally:
                await adapter.close()
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Schema discovery not supported for '{ds_type}'",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch schema: {str(e)}",
        )
