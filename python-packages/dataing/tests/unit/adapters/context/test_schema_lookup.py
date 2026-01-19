"""Tests for SchemaLookupAdapter."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from bond.tools.schema import SchemaLookupProtocol
from dataing.adapters.context.schema_lookup import SchemaLookupAdapter
from dataing.adapters.datasource.types import (
    Catalog,
    Column,
    NormalizedType,
    Schema,
    SchemaResponse,
    SourceCategory,
    SourceType,
    Table,
)


@pytest.fixture
def mock_schema_response() -> SchemaResponse:
    """Create a mock schema response."""
    return SchemaResponse(
        source_id="test-source",
        source_type=SourceType.POSTGRESQL,
        source_category=SourceCategory.DATABASE,
        fetched_at=datetime.now(),
        catalogs=[
            Catalog(
                name="main",
                schemas=[
                    Schema(
                        name="public",
                        tables=[
                            Table(
                                name="orders",
                                table_type="table",
                                native_type="TABLE",
                                native_path="public.orders",
                                columns=[
                                    Column(
                                        name="id",
                                        data_type=NormalizedType.INTEGER,
                                        native_type="int4",
                                        nullable=False,
                                    ),
                                    Column(
                                        name="customer_id",
                                        data_type=NormalizedType.INTEGER,
                                        native_type="int4",
                                        nullable=False,
                                    ),
                                ],
                            ),
                            Table(
                                name="customers",
                                table_type="table",
                                native_type="TABLE",
                                native_path="public.customers",
                                columns=[
                                    Column(
                                        name="id",
                                        data_type=NormalizedType.INTEGER,
                                        native_type="int4",
                                        nullable=False,
                                    ),
                                ],
                            ),
                        ],
                    )
                ],
            )
        ],
    )


@pytest.fixture
def mock_db_adapter(mock_schema_response: SchemaResponse) -> AsyncMock:
    """Create a mock database adapter."""
    adapter = AsyncMock()
    adapter.get_schema.return_value = mock_schema_response
    return adapter


@pytest.fixture
def mock_lineage_adapter() -> AsyncMock:
    """Create a mock lineage adapter."""
    adapter = AsyncMock()
    adapter.get_upstream.return_value = []
    adapter.get_downstream.return_value = []
    return adapter


def test_implements_protocol(mock_db_adapter: AsyncMock) -> None:
    """SchemaLookupAdapter should implement SchemaLookupProtocol."""
    lookup = SchemaLookupAdapter(mock_db_adapter)
    assert isinstance(lookup, SchemaLookupProtocol)


@pytest.mark.asyncio
async def test_get_table_schema_returns_table(mock_db_adapter: AsyncMock) -> None:
    """Test that get_table_schema returns table dict for existing table."""
    lookup = SchemaLookupAdapter(mock_db_adapter)
    result = await lookup.get_table_schema("orders")

    assert result is not None
    assert result["name"] == "orders"
    assert len(result["columns"]) == 2


@pytest.mark.asyncio
async def test_get_table_schema_returns_none_for_missing(
    mock_db_adapter: AsyncMock,
) -> None:
    """Test that get_table_schema returns None for nonexistent table."""
    lookup = SchemaLookupAdapter(mock_db_adapter)
    result = await lookup.get_table_schema("nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_get_table_schema_caches_schema(mock_db_adapter: AsyncMock) -> None:
    """Test that schema is cached after first fetch."""
    lookup = SchemaLookupAdapter(mock_db_adapter)

    await lookup.get_table_schema("orders")
    await lookup.get_table_schema("customers")

    # Should only call get_schema once (cached)
    mock_db_adapter.get_schema.assert_called_once()


@pytest.mark.asyncio
async def test_list_tables_returns_all_names(mock_db_adapter: AsyncMock) -> None:
    """Test that list_tables returns all table names."""
    lookup = SchemaLookupAdapter(mock_db_adapter)
    result = await lookup.list_tables()

    assert "public.orders" in result
    assert "public.customers" in result
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_upstream_without_lineage_returns_empty(
    mock_db_adapter: AsyncMock,
) -> None:
    """Test that get_upstream returns empty list without lineage adapter."""
    lookup = SchemaLookupAdapter(mock_db_adapter, lineage_adapter=None)
    result = await lookup.get_upstream("orders")

    assert result == []


@pytest.mark.asyncio
async def test_get_upstream_with_lineage(
    mock_db_adapter: AsyncMock, mock_lineage_adapter: AsyncMock
) -> None:
    """Test that get_upstream uses lineage adapter when available."""
    mock_lineage_adapter.get_upstream.return_value = [MagicMock(qualified_name="customers")]
    lookup = SchemaLookupAdapter(mock_db_adapter, mock_lineage_adapter)
    result = await lookup.get_upstream("orders")

    assert result == ["customers"]


@pytest.mark.asyncio
async def test_get_downstream_without_lineage_returns_empty(
    mock_db_adapter: AsyncMock,
) -> None:
    """Test that get_downstream returns empty list without lineage adapter."""
    lookup = SchemaLookupAdapter(mock_db_adapter, lineage_adapter=None)
    result = await lookup.get_downstream("orders")

    assert result == []


@pytest.mark.asyncio
async def test_get_downstream_with_lineage(
    mock_db_adapter: AsyncMock, mock_lineage_adapter: AsyncMock
) -> None:
    """Test that get_downstream uses lineage adapter when available."""
    mock_lineage_adapter.get_downstream.return_value = [MagicMock(qualified_name="order_summary")]
    lookup = SchemaLookupAdapter(mock_db_adapter, mock_lineage_adapter)
    result = await lookup.get_downstream("orders")

    assert result == ["order_summary"]


@pytest.mark.asyncio
async def test_get_table_schema_with_qualified_name(
    mock_db_adapter: AsyncMock,
) -> None:
    """Test that get_table_schema works with qualified names."""
    lookup = SchemaLookupAdapter(mock_db_adapter)
    result = await lookup.get_table_schema("public.orders")

    assert result is not None
    assert result["name"] == "orders"


@pytest.mark.asyncio
async def test_build_initial_context(mock_db_adapter: AsyncMock) -> None:
    """Test that build_initial_context returns target table and related tables."""
    lookup = SchemaLookupAdapter(mock_db_adapter, lineage_adapter=None)
    result = await lookup.build_initial_context("orders")

    assert "target_table" in result
    assert result["target_table"]["name"] == "orders"
    assert "related_tables" in result
    assert result["related_tables"] == []


@pytest.mark.asyncio
async def test_build_initial_context_with_lineage(
    mock_db_adapter: AsyncMock, mock_lineage_adapter: AsyncMock
) -> None:
    """Test that build_initial_context includes lineage when available."""
    mock_lineage_adapter.get_upstream.return_value = [MagicMock(qualified_name="customers")]
    mock_lineage_adapter.get_downstream.return_value = [MagicMock(qualified_name="order_summary")]
    lookup = SchemaLookupAdapter(mock_db_adapter, mock_lineage_adapter)
    result = await lookup.build_initial_context("orders")

    assert "target_table" in result
    assert "related_tables" in result
    assert "customers" in result["related_tables"]
    assert "order_summary" in result["related_tables"]
