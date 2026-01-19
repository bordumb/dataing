"""Schema Context - Builds schema context for investigation.

This module handles schema discovery for investigations, providing
table and column information. The LLM now accesses schema through
tools rather than having full schema dumped upfront.

Updated to use the unified SchemaResponse type from the datasource layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from dataing.adapters.datasource.types import SchemaResponse, Table

if TYPE_CHECKING:
    from dataing.adapters.datasource.base import BaseAdapter

logger = structlog.get_logger()


class SchemaContextBuilder:
    """Builds schema context from database adapters.

    This class is responsible for:
    1. Discovering tables and columns from the data source
    2. Providing table lookup and related table discovery

    The LLM now accesses schema through tools (see bond.tools.schema)
    rather than having full schema formatted upfront.

    Uses the unified SchemaResponse type from the datasource layer.
    """

    def __init__(self, max_tables: int = 20, max_columns: int = 30) -> None:
        """Initialize the schema context builder.

        Args:
            max_tables: Maximum tables to include in context.
            max_columns: Maximum columns per table to include.
        """
        self.max_tables = max_tables
        self.max_columns = max_columns

    async def build(
        self,
        adapter: BaseAdapter,
        table_filter: str | None = None,
    ) -> SchemaResponse:
        """Build schema context from a database adapter.

        Args:
            adapter: Connected data source adapter.
            table_filter: Optional pattern to filter tables (not yet used).

        Returns:
            SchemaResponse with discovered catalogs, schemas, and tables.

        Raises:
            RuntimeError: If schema discovery fails.
        """
        logger.info("discovering_schema", table_filter=table_filter)

        try:
            schema = await adapter.get_schema()
            table_count = sum(
                len(table.columns)
                for catalog in schema.catalogs
                for db_schema in catalog.schemas
                for table in db_schema.tables
            )
            logger.info("schema_discovered", table_count=table_count)
            return schema
        except Exception as e:
            logger.error("schema_discovery_failed", error=str(e))
            raise RuntimeError(f"Failed to discover schema: {e}") from e

    def _get_all_tables(self, schema: SchemaResponse) -> list[Table]:
        """Extract all tables from the nested schema structure."""
        tables = []
        for catalog in schema.catalogs:
            for db_schema in catalog.schemas:
                tables.extend(db_schema.tables)
        return tables

    def get_table_info(
        self,
        schema: SchemaResponse,
        table_name: str,
    ) -> Table | None:
        """Get detailed info for a specific table.

        Args:
            schema: SchemaResponse to search.
            table_name: Name of table to find (can be qualified or unqualified).

        Returns:
            Table if found, None otherwise.
        """
        tables = self._get_all_tables(schema)
        table_name_lower = table_name.lower()

        for table in tables:
            # Match by native_path or just name
            if (
                table.native_path.lower() == table_name_lower
                or table.name.lower() == table_name_lower
            ):
                return table
        return None

    def get_related_tables(
        self,
        schema: SchemaResponse,
        table_name: str,
    ) -> list[Table]:
        """Find tables that might be related to the given table.

        Uses simple heuristics like shared column names to identify
        potentially related tables.

        Args:
            schema: SchemaResponse to search.
            table_name: Name of the primary table.

        Returns:
            List of potentially related Table objects.
        """
        target = self.get_table_info(schema, table_name)
        if not target:
            return []

        target_cols = {col.name for col in target.columns}
        related = []
        tables = self._get_all_tables(schema)

        for table in tables:
            if table.name == target.name:
                continue

            # Check for shared column names (potential join keys)
            table_cols = {col.name for col in table.columns}
            shared = target_cols & table_cols

            # Look for common patterns like id, *_id columns
            id_cols = [c for c in shared if c.endswith("_id") or c == "id"]

            if id_cols:
                related.append(table)

        return related
