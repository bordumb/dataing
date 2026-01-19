"""Schema tools for PydanticAI agents.

This module provides agent-facing tool functions that use
RunContext to access schema lookup via dependency injection.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

from bond.tools.schema._models import (
    GetDownstreamRequest,
    GetTableSchemaRequest,
    GetUpstreamRequest,
    ListTablesRequest,
)
from bond.tools.schema._protocols import SchemaLookupProtocol


async def get_table_schema(
    ctx: RunContext[SchemaLookupProtocol],
    request: GetTableSchemaRequest,
) -> dict[str, Any] | None:
    """Get the full schema for a specific table.

    Agent Usage:
        Call this tool to get column details for a table you need to query:
        - Get join columns: "What columns does the customers table have?"
        - Check types: "What's the data type of the created_at column?"
        - Find keys: "Which columns are primary/partition keys?"

    Example:
        get_table_schema({"table_name": "customers"})

    Returns:
        Full table schema as JSON with columns, types, keys, etc.
        Returns None if table not found.
    """
    return await ctx.deps.get_table_schema(request.table_name)


async def list_tables(
    ctx: RunContext[SchemaLookupProtocol],
    request: ListTablesRequest,
) -> list[str]:
    """List all available tables in the database.

    Agent Usage:
        Call this tool to discover what tables exist:
        - Find tables: "What tables are available?"
        - Explore schema: "List all tables to understand the data model"

    Example:
        list_tables({})

    Returns:
        List of table names (may be qualified like schema.table).
    """
    return await ctx.deps.list_tables()


async def get_upstream_tables(
    ctx: RunContext[SchemaLookupProtocol],
    request: GetUpstreamRequest,
) -> list[str]:
    """Get tables that feed data into the specified table.

    Agent Usage:
        Call this tool to understand data lineage:
        - Find sources: "Where does the orders table get its data from?"
        - Trace issues: "What upstream tables might cause this anomaly?"

    Example:
        get_upstream_tables({"table_name": "orders"})

    Returns:
        List of upstream table names (data sources for this table).
    """
    return await ctx.deps.get_upstream(request.table_name)


async def get_downstream_tables(
    ctx: RunContext[SchemaLookupProtocol],
    request: GetDownstreamRequest,
) -> list[str]:
    """Get tables that consume data from the specified table.

    Agent Usage:
        Call this tool to understand data impact:
        - Find dependents: "What tables use data from orders?"
        - Assess impact: "What would be affected by this anomaly?"

    Example:
        get_downstream_tables({"table_name": "orders"})

    Returns:
        List of downstream table names (tables that depend on this one).
    """
    return await ctx.deps.get_downstream(request.table_name)


# Export as toolset for BondAgent
schema_toolset: list[Tool[SchemaLookupProtocol]] = [
    Tool(get_table_schema),
    Tool(list_tables),
    Tool(get_upstream_tables),
    Tool(get_downstream_tables),
]
