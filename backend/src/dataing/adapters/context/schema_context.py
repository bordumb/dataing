"""Schema Context - Builds and formats schema context for LLM prompts.

This module handles schema discovery and formatting for the LLM,
providing clear table and column information that helps the AI
generate accurate SQL queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from dataing.core.domain_types import SchemaContext as SchemaContextData
from dataing.core.domain_types import TableSchema

if TYPE_CHECKING:
    from dataing.core.interfaces import DatabaseAdapter

logger = structlog.get_logger()


class SchemaContextBuilder:
    """Builds schema context from database adapters.

    This class is responsible for:
    1. Discovering tables and columns from the data source
    2. Formatting schema information for LLM prompts
    3. Filtering tables by pattern when needed

    Note: Named SchemaContextBuilder to avoid conflict with
    SchemaContext domain type.
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
        adapter: DatabaseAdapter,
        table_filter: str | None = None,
    ) -> SchemaContextData:
        """Build schema context from a database adapter.

        Args:
            adapter: Connected database adapter.
            table_filter: Optional pattern to filter tables.

        Returns:
            SchemaContextData with discovered tables.

        Raises:
            RuntimeError: If schema discovery fails.
        """
        logger.info("discovering_schema", table_filter=table_filter)

        try:
            schema = await adapter.get_schema(table_filter)
            logger.info("schema_discovered", tables_count=len(schema.tables))
            return schema
        except Exception as e:
            logger.error("schema_discovery_failed", error=str(e))
            raise RuntimeError(f"Failed to discover schema: {e}") from e

    def format_for_llm(self, schema: SchemaContextData) -> str:
        """Format schema as markdown for LLM prompt.

        Creates a clear, structured representation of the schema
        that helps the LLM understand available tables and columns.

        Args:
            schema: SchemaContextData to format.

        Returns:
            Markdown-formatted schema string.
        """
        if not schema.tables:
            return "No tables available."

        lines = [
            "## Available Tables",
            "",
            "Use ONLY these tables and columns in your SQL queries.",
            "",
        ]

        for table in schema.tables[: self.max_tables]:
            lines.append(f"### {table.table_name}")
            lines.append("")
            lines.append("| Column | Type |")
            lines.append("|--------|------|")

            for col in table.columns[: self.max_columns]:
                col_type = table.column_types.get(col, "unknown")
                lines.append(f"| {col} | {col_type} |")

            if len(table.columns) > self.max_columns:
                remaining = len(table.columns) - self.max_columns
                lines.append(f"| ... | ({remaining} more columns) |")

            lines.append("")

        if len(schema.tables) > self.max_tables:
            remaining = len(schema.tables) - self.max_tables
            lines.append(f"*({remaining} more tables not shown)*")
            lines.append("")

        lines.append("**IMPORTANT**: Only use tables and columns listed above.")
        lines.append("Do NOT invent or assume other tables exist.")

        return "\n".join(lines)

    def format_compact(self, schema: SchemaContextData) -> str:
        """Format schema in compact form for smaller context windows.

        Args:
            schema: SchemaContextData to format.

        Returns:
            Compact schema string.
        """
        if not schema.tables:
            return "No tables."

        lines = ["Tables:"]
        for table in schema.tables[: self.max_tables]:
            cols = ", ".join(table.columns[: self.max_columns])
            if len(table.columns) > self.max_columns:
                cols += f" (+{len(table.columns) - self.max_columns} more)"
            lines.append(f"  {table.table_name}: {cols}")

        return "\n".join(lines)

    def get_table_info(
        self,
        schema: SchemaContextData,
        table_name: str,
    ) -> TableSchema | None:
        """Get detailed info for a specific table.

        Args:
            schema: SchemaContextData to search.
            table_name: Name of table to find.

        Returns:
            TableSchema if found, None otherwise.
        """
        return schema.get_table(table_name)

    def get_related_tables(
        self,
        schema: SchemaContextData,
        table_name: str,
    ) -> list[TableSchema]:
        """Find tables that might be related to the given table.

        Uses simple heuristics like shared column names to identify
        potentially related tables.

        Args:
            schema: SchemaContextData to search.
            table_name: Name of the primary table.

        Returns:
            List of potentially related TableSchema objects.
        """
        target = schema.get_table(table_name)
        if not target:
            return []

        target_cols = set(target.columns)
        related = []

        for table in schema.tables:
            if table.table_name == table_name:
                continue

            # Check for shared column names (potential join keys)
            table_cols = set(table.columns)
            shared = target_cols & table_cols

            # Look for common patterns like id, *_id columns
            id_cols = [c for c in shared if c.endswith("_id") or c == "id"]

            if id_cols:
                related.append(table)

        return related
