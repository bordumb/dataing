"""Pydantic models for schema tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GetTableSchemaRequest(BaseModel):
    """Request to get schema for a specific table."""

    table_name: str = Field(..., description="Table name (can be qualified like schema.table)")


class ListTablesRequest(BaseModel):
    """Request to list available tables."""

    pattern: str | None = Field(None, description="Optional glob pattern to filter tables")


class GetUpstreamRequest(BaseModel):
    """Request to get upstream dependencies."""

    table_name: str = Field(..., description="Table name to get upstream for")


class GetDownstreamRequest(BaseModel):
    """Request to get downstream dependencies."""

    table_name: str = Field(..., description="Table name to get downstream for")


class ColumnSchema(BaseModel):
    """Schema information for a single column."""

    name: str
    data_type: str
    native_type: str | None = None
    nullable: bool = True
    is_primary_key: bool = False
    is_partition_key: bool = False
    description: str | None = None
    default_value: str | None = None


class TableSchema(BaseModel):
    """Schema information for a table."""

    name: str
    columns: list[ColumnSchema]
    schema_name: str | None = None
    catalog_name: str | None = None
    description: str | None = None

    @property
    def qualified_name(self) -> str:
        """Get fully qualified table name."""
        parts = []
        if self.catalog_name:
            parts.append(self.catalog_name)
        if self.schema_name:
            parts.append(self.schema_name)
        parts.append(self.name)
        return ".".join(parts)
