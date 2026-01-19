"""Tests for schema lookup protocol."""

from typing import Any

from bond.tools.schema._protocols import SchemaLookupProtocol


def test_protocol_is_runtime_checkable() -> None:
    """Protocol should be runtime checkable for isinstance."""
    assert getattr(SchemaLookupProtocol, "_is_runtime_protocol", False)


def test_mock_implements_protocol() -> None:
    """A mock class should satisfy the protocol."""

    class MockSchemaLookup:
        """Mock implementation of SchemaLookupProtocol."""

        async def get_table_schema(self, table_name: str) -> dict[str, Any] | None:
            """Get schema for a table."""
            return None

        async def list_tables(self) -> list[str]:
            """List all tables."""
            return []

        async def get_upstream(self, table_name: str) -> list[str]:
            """Get upstream dependencies."""
            return []

        async def get_downstream(self, table_name: str) -> list[str]:
            """Get downstream dependencies."""
            return []

    mock = MockSchemaLookup()
    assert isinstance(mock, SchemaLookupProtocol)


def test_incomplete_implementation_not_protocol() -> None:
    """An incomplete implementation should not satisfy the protocol."""

    class IncompleteSchemaLookup:
        """Missing some protocol methods."""

        async def get_table_schema(self, table_name: str) -> dict[str, Any] | None:
            """Get schema for a table."""
            return None

        # Missing list_tables, get_upstream, get_downstream

    incomplete = IncompleteSchemaLookup()
    assert not isinstance(incomplete, SchemaLookupProtocol)
