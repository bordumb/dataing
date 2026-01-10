"""Base adapter interface and abstract base classes.

This module defines the abstract base class that all adapters must implement,
providing a consistent interface for connecting to and querying data sources.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Self

from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    ConnectionTestResult,
    SchemaFilter,
    SchemaResponse,
    SourceCategory,
    SourceType,
)


class BaseAdapter(ABC):
    """Abstract base class for all data source adapters.

    All adapters must implement this interface to provide:
    - Connection management (connect/disconnect)
    - Connection testing
    - Schema discovery
    - Context manager support

    Attributes:
        config: Configuration dictionary for the adapter.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the adapter with configuration.

        Args:
            config: Configuration dictionary specific to the adapter type.
        """
        self._config = config
        self._connected = False

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the data source.

        Should be called before any other operations.

        Raises:
            ConnectionFailedError: If connection cannot be established.
            AuthenticationFailedError: If credentials are invalid.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the data source.

        Should be called during cleanup.
        """
        ...

    @abstractmethod
    async def test_connection(self) -> ConnectionTestResult:
        """Test connectivity to the data source.

        Returns:
            ConnectionTestResult with success status and details.
        """
        ...

    @abstractmethod
    async def get_schema(self, filter: SchemaFilter | None = None) -> SchemaResponse:
        """Discover schema from the data source.

        Args:
            filter: Optional filter for schema discovery.

        Returns:
            SchemaResponse with all discovered catalogs, schemas, and tables.

        Raises:
            SchemaFetchFailedError: If schema cannot be retrieved.
        """
        ...

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.disconnect()

    @property
    def is_connected(self) -> bool:
        """Check if adapter is currently connected."""
        return self._connected

    def _build_schema_response(
        self,
        source_id: str,
        catalogs: list[dict[str, Any]],
    ) -> SchemaResponse:
        """Helper to build a SchemaResponse from catalog data.

        Args:
            source_id: ID of the data source.
            catalogs: List of catalog dictionaries.

        Returns:
            Properly formatted SchemaResponse.
        """
        from dataing.adapters.datasource.types import (
            Catalog,
            Column,
            Schema,
            Table,
        )

        parsed_catalogs = []
        for cat_data in catalogs:
            schemas = []
            for schema_data in cat_data.get("schemas", []):
                tables = []
                for table_data in schema_data.get("tables", []):
                    columns = [Column(**col_data) for col_data in table_data.get("columns", [])]
                    tables.append(
                        Table(
                            name=table_data["name"],
                            table_type=table_data.get("table_type", "table"),
                            native_type=table_data.get("native_type", "TABLE"),
                            native_path=table_data.get("native_path", table_data["name"]),
                            columns=columns,
                            row_count=table_data.get("row_count"),
                            size_bytes=table_data.get("size_bytes"),
                            last_modified=table_data.get("last_modified"),
                            description=table_data.get("description"),
                        )
                    )
                schemas.append(
                    Schema(
                        name=schema_data.get("name", "default"),
                        tables=tables,
                    )
                )
            parsed_catalogs.append(
                Catalog(
                    name=cat_data.get("name", "default"),
                    schemas=schemas,
                )
            )

        # Determine source category
        source_category = self._get_source_category()

        return SchemaResponse(
            source_id=source_id,
            source_type=self.source_type,
            source_category=source_category,
            fetched_at=datetime.now(),
            catalogs=parsed_catalogs,
        )

    def _get_source_category(self) -> SourceCategory:
        """Determine source category based on source type."""
        from dataing.adapters.datasource.types import SourceCategory, SourceType

        sql_types = {
            SourceType.POSTGRESQL,
            SourceType.MYSQL,
            SourceType.TRINO,
            SourceType.SNOWFLAKE,
            SourceType.BIGQUERY,
            SourceType.REDSHIFT,
            SourceType.DUCKDB,
            SourceType.SQLITE,
            SourceType.MONGODB,
            SourceType.DYNAMODB,
            SourceType.CASSANDRA,
        }
        api_types = {SourceType.SALESFORCE, SourceType.HUBSPOT, SourceType.STRIPE}
        filesystem_types = {
            SourceType.S3,
            SourceType.GCS,
            SourceType.HDFS,
            SourceType.LOCAL_FILE,
        }

        if self.source_type in sql_types:
            return SourceCategory.DATABASE
        elif self.source_type in api_types:
            return SourceCategory.API
        elif self.source_type in filesystem_types:
            return SourceCategory.FILESYSTEM
        else:
            return SourceCategory.DATABASE
