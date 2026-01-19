"""Protocol definitions for schema lookup tools.

This module defines the interface that schema lookup implementations
must satisfy. The protocol is runtime-checkable for flexibility.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SchemaLookupProtocol(Protocol):
    """Protocol for schema lookup operations.

    Implementations provide access to database schema information
    and lineage data for agent tools.
    """

    async def get_table_schema(self, table_name: str) -> dict[str, Any] | None:
        """Get schema for a specific table.

        Args:
            table_name: Name of the table (can be qualified like schema.table).

        Returns:
            Table schema as dict with columns, types, etc. or None if not found.
        """
        ...

    async def list_tables(self) -> list[str]:
        """List all available table names.

        Returns:
            List of table names (may be qualified).
        """
        ...

    async def get_upstream(self, table_name: str) -> list[str]:
        """Get upstream dependencies for a table.

        Args:
            table_name: Name of the table.

        Returns:
            List of upstream table names.
        """
        ...

    async def get_downstream(self, table_name: str) -> list[str]:
        """Get downstream dependencies for a table.

        Args:
            table_name: Name of the table.

        Returns:
            List of downstream table names.
        """
        ...
