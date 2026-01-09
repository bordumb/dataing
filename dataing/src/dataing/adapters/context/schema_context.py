"""Schema Context - Builds and formats schema context for LLM prompts.

This module handles schema discovery and formatting for the LLM,
providing clear table and column information that helps the AI
generate accurate SQL queries.

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
    2. Formatting schema information for LLM prompts
    3. Filtering tables by pattern when needed

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

    def format_for_llm(self, schema: SchemaResponse) -> str:
        """Format schema as markdown for LLM prompt.

        Creates a clear, structured representation of the schema
        that helps the LLM understand available tables and columns.

        Args:
            schema: SchemaResponse to format.

        Returns:
            Markdown-formatted schema string.
        """
        tables = self._get_all_tables(schema)

        if not tables:
            return "No tables available."

        lines = [
            "## Available Tables",
            "",
            "Use ONLY these tables and columns in your SQL queries.",
            "",
        ]

        for table in tables[: self.max_tables]:
            lines.append(f"### {table.native_path}")
            lines.append("")
            lines.append("| Column | Type | Nullable |")
            lines.append("|--------|------|----------|")

            for col in table.columns[: self.max_columns]:
                nullable = "Yes" if col.nullable else "No"
                lines.append(f"| {col.name} | {col.data_type.value} | {nullable} |")

            if len(table.columns) > self.max_columns:
                remaining = len(table.columns) - self.max_columns
                lines.append(f"| ... | ({remaining} more columns) | |")

            lines.append("")

        if len(tables) > self.max_tables:
            remaining = len(tables) - self.max_tables
            lines.append(f"*({remaining} more tables not shown)*")
            lines.append("")

        lines.append("**IMPORTANT**: Only use tables and columns listed above.")
        lines.append("Do NOT invent or assume other tables exist.")

        return "\n".join(lines)

    def format_compact(self, schema: SchemaResponse) -> str:
        """Format schema in compact form for smaller context windows.

        Args:
            schema: SchemaResponse to format.

        Returns:
            Compact schema string.
        """
        tables = self._get_all_tables(schema)

        if not tables:
            return "No tables."

        lines = ["Tables:"]
        for table in tables[: self.max_tables]:
            col_names = [col.name for col in table.columns[: self.max_columns]]
            cols = ", ".join(col_names)
            if len(table.columns) > self.max_columns:
                cols += f" (+{len(table.columns) - self.max_columns} more)"
            lines.append(f"  {table.native_path}: {cols}")

        return "\n".join(lines)

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
