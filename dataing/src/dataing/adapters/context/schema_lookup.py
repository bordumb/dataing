"""Schema lookup adapter for agent tools.

Implements SchemaLookupProtocol from bond using existing
BaseAdapter and LineageAdapter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from dataing.adapters.datasource.types import SchemaResponse, Table
from dataing.adapters.lineage import DatasetId

if TYPE_CHECKING:
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.adapters.lineage import LineageAdapter

logger = structlog.get_logger()


class SchemaLookupAdapter:
    """Implements SchemaLookupProtocol using existing adapters.

    This adapter bridges the bond schema tools with dataing's
    database and lineage adapters. It caches schema discovery
    to avoid repeated queries.
    """

    def __init__(
        self,
        db_adapter: BaseAdapter,
        lineage_adapter: LineageAdapter | None = None,
    ) -> None:
        """Initialize the schema lookup adapter.

        Args:
            db_adapter: Connected database adapter for schema discovery.
            lineage_adapter: Optional lineage adapter for dependency info.
        """
        self.db_adapter = db_adapter
        self.lineage_adapter = lineage_adapter
        self._schema_cache: SchemaResponse | None = None

    async def _ensure_schema(self) -> SchemaResponse:
        """Ensure schema is loaded, fetching if needed."""
        if self._schema_cache is None:
            logger.info("fetching_schema")
            self._schema_cache = await self.db_adapter.get_schema()
            logger.info(f"schema_cached, table_count={self._count_tables()}")
        return self._schema_cache

    def _count_tables(self) -> int:
        """Count total tables in cached schema."""
        if self._schema_cache is None:
            return 0
        return sum(
            len(db_schema.tables)
            for catalog in self._schema_cache.catalogs
            for db_schema in catalog.schemas
        )

    def _get_all_tables(self, schema: SchemaResponse) -> list[Table]:
        """Extract all tables from nested schema structure."""
        tables = []
        for catalog in schema.catalogs:
            for db_schema in catalog.schemas:
                tables.extend(db_schema.tables)
        return tables

    def _find_table(self, schema: SchemaResponse, table_name: str) -> Table | None:
        """Find a table by name (qualified or unqualified)."""
        table_name_lower = table_name.lower()
        for table in self._get_all_tables(schema):
            if (
                table.name.lower() == table_name_lower
                or table.native_path.lower() == table_name_lower
            ):
                return table
        return None

    def _table_to_dict(self, table: Table) -> dict[str, Any]:
        """Convert Table to dict for JSON serialization."""
        return {
            "name": table.name,
            "native_path": table.native_path,
            "columns": [
                {
                    "name": col.name,
                    "data_type": col.data_type.value,
                    "native_type": col.native_type,
                    "nullable": col.nullable,
                    "is_primary_key": col.is_primary_key,
                    "is_partition_key": col.is_partition_key,
                    "description": col.description,
                    "default_value": col.default_value,
                }
                for col in table.columns
            ],
        }

    async def get_table_schema(self, table_name: str) -> dict[str, Any] | None:
        """Get schema for a specific table."""
        schema = await self._ensure_schema()
        table = self._find_table(schema, table_name)
        if table is None:
            return None
        return self._table_to_dict(table)

    async def list_tables(self) -> list[str]:
        """List all available table names."""
        schema = await self._ensure_schema()
        tables = self._get_all_tables(schema)
        return [t.native_path for t in tables]

    async def get_upstream(self, table_name: str) -> list[str]:
        """Get upstream dependencies for a table."""
        if self.lineage_adapter is None:
            return []

        try:
            dataset_id = DatasetId.from_urn(table_name)
            upstream = await self.lineage_adapter.get_upstream(dataset_id, depth=1)
            return [ds.qualified_name for ds in upstream]
        except Exception as e:
            logger.warning(f"get_upstream_failed, table={table_name}, error={e!s}")
            return []

    async def get_downstream(self, table_name: str) -> list[str]:
        """Get downstream dependencies for a table."""
        if self.lineage_adapter is None:
            return []

        try:
            dataset_id = DatasetId.from_urn(table_name)
            downstream = await self.lineage_adapter.get_downstream(dataset_id, depth=1)
            return [ds.qualified_name for ds in downstream]
        except Exception as e:
            logger.warning(f"get_downstream_failed, table={table_name}, error={e!s}")
            return []

    async def build_initial_context(self, target_table_name: str) -> dict[str, Any]:
        """Build initial context with target table + related names.

        This is the minimal context injected at investigation start.
        Agent can fetch more details on demand via tools.

        Args:
            target_table_name: Name of the table with the anomaly.

        Returns:
            Dict with target_table schema and related_tables names.
        """
        target_schema = await self.get_table_schema(target_table_name)
        upstream = await self.get_upstream(target_table_name)
        downstream = await self.get_downstream(target_table_name)

        return {
            "target_table": target_schema,
            "related_tables": upstream + downstream,
        }
