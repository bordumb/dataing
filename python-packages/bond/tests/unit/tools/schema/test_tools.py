"""Tests for schema tool functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from bond.tools.schema._models import (
    GetDownstreamRequest,
    GetTableSchemaRequest,
    GetUpstreamRequest,
    ListTablesRequest,
)
from bond.tools.schema.tools import (
    get_downstream_tables,
    get_table_schema,
    get_upstream_tables,
    list_tables,
)


class MockSchemaLookup:
    """Test implementation of SchemaLookupProtocol."""

    def __init__(
        self,
        tables: dict[str, dict[str, Any]] | None = None,
        upstream: dict[str, list[str]] | None = None,
        downstream: dict[str, list[str]] | None = None,
    ) -> None:
        """Initialize the mock schema lookup."""
        self.tables = tables or {}
        self.upstream = upstream or {}
        self.downstream = downstream or {}

    async def get_table_schema(self, table_name: str) -> dict[str, Any] | None:
        """Get schema for a specific table."""
        return self.tables.get(table_name)

    async def list_tables(self) -> list[str]:
        """List all available table names."""
        return list(self.tables.keys())

    async def get_upstream(self, table_name: str) -> list[str]:
        """Get upstream dependencies for a table."""
        return self.upstream.get(table_name, [])

    async def get_downstream(self, table_name: str) -> list[str]:
        """Get downstream dependencies for a table."""
        return self.downstream.get(table_name, [])


@pytest.fixture
def mock_ctx() -> MagicMock:
    """Create a mock RunContext with schema lookup deps."""
    ctx = MagicMock()
    ctx.deps = MockSchemaLookup(
        tables={
            "orders": {
                "name": "orders",
                "columns": [{"name": "id", "data_type": "integer"}],
            },
        },
        upstream={"orders": ["customers"]},
        downstream={"orders": ["order_items"]},
    )
    return ctx


@pytest.mark.asyncio
async def test_get_table_schema_returns_table(mock_ctx: MagicMock) -> None:
    """Test get_table_schema returns table schema when found."""
    request = GetTableSchemaRequest(table_name="orders")
    result = await get_table_schema(mock_ctx, request)
    assert result is not None
    assert result["name"] == "orders"


@pytest.mark.asyncio
async def test_get_table_schema_returns_none_for_missing(mock_ctx: MagicMock) -> None:
    """Test get_table_schema returns None for missing table."""
    request = GetTableSchemaRequest(table_name="nonexistent")
    result = await get_table_schema(mock_ctx, request)
    assert result is None


@pytest.mark.asyncio
async def test_list_tables_returns_names(mock_ctx: MagicMock) -> None:
    """Test list_tables returns all table names."""
    request = ListTablesRequest()
    result = await list_tables(mock_ctx, request)
    assert result == ["orders"]


@pytest.mark.asyncio
async def test_get_upstream_tables_returns_dependencies(mock_ctx: MagicMock) -> None:
    """Test get_upstream_tables returns upstream dependencies."""
    request = GetUpstreamRequest(table_name="orders")
    result = await get_upstream_tables(mock_ctx, request)
    assert result == ["customers"]


@pytest.mark.asyncio
async def test_get_downstream_tables_returns_dependencies(mock_ctx: MagicMock) -> None:
    """Test get_downstream_tables returns downstream dependencies."""
    request = GetDownstreamRequest(table_name="orders")
    result = await get_downstream_tables(mock_ctx, request)
    assert result == ["order_items"]
