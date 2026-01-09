"""Type definitions for the unified data source layer.

This module defines all the data structures used across all adapters,
ensuring consistent JSON output regardless of the underlying source.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    """Supported data source types."""

    # SQL Databases
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    TRINO = "trino"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    REDSHIFT = "redshift"
    DUCKDB = "duckdb"

    # NoSQL Databases
    MONGODB = "mongodb"
    DYNAMODB = "dynamodb"
    CASSANDRA = "cassandra"

    # APIs
    SALESFORCE = "salesforce"
    HUBSPOT = "hubspot"
    STRIPE = "stripe"

    # File Systems
    S3 = "s3"
    GCS = "gcs"
    HDFS = "hdfs"
    LOCAL_FILE = "local_file"


class SourceCategory(str, Enum):
    """Categories of data sources."""

    DATABASE = "database"
    API = "api"
    FILESYSTEM = "filesystem"


class NormalizedType(str, Enum):
    """Normalized type system that maps all source types."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    TIMESTAMP = "timestamp"
    BINARY = "binary"
    JSON = "json"
    ARRAY = "array"
    MAP = "map"
    STRUCT = "struct"
    UNKNOWN = "unknown"


class QueryLanguage(str, Enum):
    """Query languages supported by adapters."""

    SQL = "sql"
    SOQL = "soql"  # Salesforce Object Query Language
    MQL = "mql"  # MongoDB Query Language
    SCAN_ONLY = "scan_only"  # No query language, scan only


class ColumnStats(BaseModel):
    """Statistics for a column."""

    model_config = ConfigDict(frozen=True)

    null_count: int
    null_rate: float
    distinct_count: int | None = None
    min_value: str | None = None
    max_value: str | None = None
    sample_values: list[str] = Field(default_factory=list)


class Column(BaseModel):
    """Unified column representation."""

    model_config = ConfigDict(frozen=True)

    name: str
    data_type: NormalizedType
    native_type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_partition_key: bool = False
    description: str | None = None
    default_value: str | None = None
    stats: ColumnStats | None = None


class Table(BaseModel):
    """Unified table representation."""

    model_config = ConfigDict(frozen=True)

    name: str
    table_type: Literal["table", "view", "external", "object", "collection", "file"]
    native_type: str
    native_path: str
    columns: list[Column]
    row_count: int | None = None
    size_bytes: int | None = None
    last_modified: datetime | None = None
    description: str | None = None


class Schema(BaseModel):
    """Schema within a catalog."""

    model_config = ConfigDict(frozen=True)

    name: str
    tables: list[Table]


class Catalog(BaseModel):
    """Catalog containing schemas."""

    model_config = ConfigDict(frozen=True)

    name: str
    schemas: list[Schema]


class SchemaResponse(BaseModel):
    """Unified schema response from any adapter."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    source_type: SourceType
    source_category: SourceCategory
    fetched_at: datetime
    catalogs: list[Catalog]

    def get_all_tables(self) -> list[Table]:
        """Get all tables from the nested catalog/schema structure."""
        tables = []
        for catalog in self.catalogs:
            for schema in catalog.schemas:
                tables.extend(schema.tables)
        return tables

    def table_count(self) -> int:
        """Count total tables across all catalogs and schemas."""
        return sum(len(schema.tables) for catalog in self.catalogs for schema in catalog.schemas)

    def is_empty(self) -> bool:
        """Check if schema has no tables. Used for fail-fast validation."""
        return self.table_count() == 0

    def to_prompt_string(self, max_tables: int = 10, max_columns: int = 15) -> str:
        """Format schema for LLM prompt.

        Args:
            max_tables: Maximum tables to include.
            max_columns: Maximum columns per table.

        Returns:
            Formatted string for LLM consumption.
        """
        tables = self.get_all_tables()
        if not tables:
            return "No tables available."

        lines = ["AVAILABLE TABLES AND COLUMNS (USE ONLY THESE):"]

        for table in tables[:max_tables]:
            lines.append(f"\n{table.native_path}")
            for col in table.columns[:max_columns]:
                lines.append(f"   - {col.name} ({col.data_type.value})")
            if len(table.columns) > max_columns:
                lines.append(f"   ... and {len(table.columns) - max_columns} more columns")

        if len(tables) > max_tables:
            lines.append(f"\n... and {len(tables) - max_tables} more tables")

        lines.append("\nCRITICAL: Use ONLY the tables and columns listed above.")
        lines.append("DO NOT invent tables or columns.")

        return "\n".join(lines)

    def get_table_names(self) -> list[str]:
        """Get list of all table names for LLM context."""
        return [table.native_path for table in self.get_all_tables()]


class SchemaFilter(BaseModel):
    """Filter for schema discovery."""

    model_config = ConfigDict(frozen=True)

    table_pattern: str | None = None
    schema_pattern: str | None = None
    catalog_pattern: str | None = None
    include_views: bool = True
    max_tables: int = 1000


class QueryResult(BaseModel):
    """Result of executing a query."""

    model_config = ConfigDict(frozen=True)

    columns: list[dict[str, Any]]  # [{"name": "col", "data_type": "string"}]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = False
    execution_time_ms: int | None = None

    def to_summary(self, max_rows: int = 5) -> str:
        """Create a summary of the query results for LLM interpretation.

        Args:
            max_rows: Maximum number of rows to include in the summary.

        Returns:
            Formatted summary string.
        """
        if not self.rows:
            return "No rows returned"

        col_names = [col.get("name", "?") for col in self.columns]
        lines = [f"Columns: {', '.join(col_names)}"]
        lines.append(f"Total rows: {self.row_count}")
        if self.truncated:
            lines.append("(Results truncated)")
        lines.append("\nSample rows:")

        for row in self.rows[:max_rows]:
            row_str = ", ".join(f"{k}={v}" for k, v in row.items())
            lines.append(f"  {row_str}")

        if len(self.rows) > max_rows:
            lines.append(f"  ... and {len(self.rows) - max_rows} more rows")

        return "\n".join(lines)


class ConnectionTestResult(BaseModel):
    """Result of testing a connection."""

    model_config = ConfigDict(frozen=True)

    success: bool
    latency_ms: int | None = None
    server_version: str | None = None
    message: str
    error_code: str | None = None


class AdapterCapabilities(BaseModel):
    """Capabilities of an adapter."""

    model_config = ConfigDict(frozen=True)

    supports_sql: bool = False
    supports_sampling: bool = False
    supports_row_count: bool = False
    supports_column_stats: bool = False
    supports_preview: bool = False
    supports_write: bool = False
    rate_limit_requests_per_minute: int | None = None
    max_concurrent_queries: int = 1
    query_language: QueryLanguage = QueryLanguage.SCAN_ONLY


class FieldGroup(BaseModel):
    """Group of configuration fields."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    description: str | None = None
    collapsed_by_default: bool = False


class ConfigField(BaseModel):
    """Configuration field for connection forms."""

    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    type: Literal["string", "integer", "boolean", "enum", "secret", "file", "json"]
    required: bool
    group: str
    default_value: Any | None = None
    placeholder: str | None = None
    min_value: int | None = None
    max_value: int | None = None
    pattern: str | None = None
    options: list[dict[str, str]] | None = None
    show_if: dict[str, Any] | None = None
    description: str | None = None
    help_url: str | None = None


class ConfigSchema(BaseModel):
    """Configuration schema for an adapter."""

    model_config = ConfigDict(frozen=True)

    fields: list[ConfigField]
    field_groups: list[FieldGroup]


class SourceTypeDefinition(BaseModel):
    """Complete definition of a source type."""

    model_config = ConfigDict(frozen=True)

    type: SourceType
    display_name: str
    category: SourceCategory
    icon: str
    description: str
    capabilities: AdapterCapabilities
    config_schema: ConfigSchema


class DataSourceStats(BaseModel):
    """Statistics for a data source."""

    model_config = ConfigDict(frozen=True)

    table_count: int
    total_row_count: int | None = None
    total_size_bytes: int | None = None


class DataSourceResponse(BaseModel):
    """Response for a data source."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    source_type: SourceType
    source_category: SourceCategory
    status: Literal["connected", "disconnected", "error"]
    created_at: datetime
    last_synced_at: datetime | None = None
    stats: DataSourceStats | None = None
