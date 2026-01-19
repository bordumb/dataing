"""Tests for schema tool models."""

import pytest
from pydantic import ValidationError

from bond.tools.schema._models import (
    ColumnSchema,
    GetDownstreamRequest,
    GetTableSchemaRequest,
    GetUpstreamRequest,
    ListTablesRequest,
    TableSchema,
)


class TestGetTableSchemaRequest:
    """Tests for GetTableSchemaRequest model."""

    def test_creates_request(self):
        """Test creating a valid request."""
        req = GetTableSchemaRequest(table_name="orders")
        assert req.table_name == "orders"

    def test_requires_table_name(self):
        """Test that table_name is required."""
        with pytest.raises(ValidationError):
            GetTableSchemaRequest()


class TestListTablesRequest:
    """Tests for ListTablesRequest model."""

    def test_creates_request_with_defaults(self):
        """Test creating a request with default values."""
        req = ListTablesRequest()
        assert req.pattern is None

    def test_accepts_pattern(self):
        """Test that pattern is accepted."""
        req = ListTablesRequest(pattern="order*")
        assert req.pattern == "order*"


class TestGetUpstreamRequest:
    """Tests for GetUpstreamRequest model."""

    def test_creates_request(self):
        """Test creating a valid request."""
        req = GetUpstreamRequest(table_name="orders")
        assert req.table_name == "orders"


class TestGetDownstreamRequest:
    """Tests for GetDownstreamRequest model."""

    def test_creates_request(self):
        """Test creating a valid request."""
        req = GetDownstreamRequest(table_name="orders")
        assert req.table_name == "orders"


class TestColumnSchema:
    """Tests for ColumnSchema model."""

    def test_creates_column(self):
        """Test creating a column with minimal fields."""
        col = ColumnSchema(
            name="id",
            data_type="integer",
            nullable=False,
        )
        assert col.name == "id"
        assert col.is_primary_key is False  # default

    def test_creates_column_with_all_fields(self):
        """Test creating a column with all fields."""
        col = ColumnSchema(
            name="id",
            data_type="integer",
            native_type="BIGINT",
            nullable=False,
            is_primary_key=True,
            is_partition_key=False,
            description="Primary key",
        )
        assert col.is_primary_key is True
        assert col.native_type == "BIGINT"


class TestTableSchema:
    """Tests for TableSchema model."""

    def test_creates_table(self):
        """Test creating a table with columns."""
        table = TableSchema(
            name="orders",
            columns=[
                ColumnSchema(name="id", data_type="integer", nullable=False),
            ],
        )
        assert table.name == "orders"
        assert len(table.columns) == 1

    def test_creates_table_with_qualified_name(self):
        """Test creating a table with qualified name components."""
        table = TableSchema(
            name="orders",
            schema_name="public",
            catalog_name="main",
            columns=[],
        )
        assert table.qualified_name == "main.public.orders"
