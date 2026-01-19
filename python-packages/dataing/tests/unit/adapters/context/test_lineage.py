"""Unit tests for lineage clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataing.adapters.context.lineage import (
    LineageContext,
    MockLineageClient,
    OpenLineageClient,
)


class TestOpenLineageClient:
    """Tests for OpenLineageClient."""

    @pytest.fixture
    def client(self) -> OpenLineageClient:
        """Return an OpenLineage client."""
        return OpenLineageClient(base_url="http://localhost:5000", timeout=10)

    def test_init_strips_trailing_slash(self) -> None:
        """Test that trailing slashes are stripped from base_url."""
        client = OpenLineageClient(base_url="http://localhost:5000/")
        assert client.base_url == "http://localhost:5000"

    async def test_get_lineage_parses_namespace_and_name(
        self,
        client: OpenLineageClient,
    ) -> None:
        """Test that dataset_id is parsed into namespace and name."""
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"datasets": []}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.get_lineage("public.orders")

            assert result.target == "public.orders"
            # Verify correct API endpoints were called
            calls = mock_client.get.call_args_list
            assert len(calls) == 2
            assert "/public/orders/upstream" in str(calls[0])
            assert "/public/orders/downstream" in str(calls[1])

    async def test_get_lineage_handles_no_namespace(
        self,
        client: OpenLineageClient,
    ) -> None:
        """Test handling of dataset_id without namespace."""
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"datasets": []}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await client.get_lineage("orders")

            assert result.target == "orders"
            # Should use 'default' namespace
            calls = mock_client.get.call_args_list
            assert "/default/orders/upstream" in str(calls[0])

    def test_extract_datasets(self, client: OpenLineageClient) -> None:
        """Test _extract_datasets extracts dataset names correctly."""
        data = {
            "datasets": [
                {"namespace": "public", "name": "users"},
                {"namespace": "staging", "name": "products"},
                {"namespace": "", "name": "orphan_table"},
            ]
        }

        result = client._extract_datasets(data)

        assert "public.users" in result
        assert "staging.products" in result
        assert "orphan_table" in result

    def test_extract_datasets_empty(self, client: OpenLineageClient) -> None:
        """Test _extract_datasets handles empty data."""
        assert client._extract_datasets({}) == []
        assert client._extract_datasets({"datasets": []}) == []


class TestMockLineageClient:
    """Tests for MockLineageClient."""

    def test_init_with_empty_lineage_map(self) -> None:
        """Test initialization with no lineage map."""
        client = MockLineageClient()
        assert client.lineage_map == {}

    def test_init_with_lineage_map(self) -> None:
        """Test initialization with predefined lineage map."""
        lineage = LineageContext(
            target="public.orders",
            upstream=("public.users",),
            downstream=(),
        )
        client = MockLineageClient(lineage_map={"public.orders": lineage})

        assert "public.orders" in client.lineage_map

    async def test_get_lineage_returns_mapped_context(self) -> None:
        """Test get_lineage returns predefined context."""
        lineage = LineageContext(
            target="public.orders",
            upstream=("public.users",),
            downstream=("public.summary",),
        )
        client = MockLineageClient(lineage_map={"public.orders": lineage})

        result = await client.get_lineage("public.orders")

        assert result.target == "public.orders"
        assert "public.users" in result.upstream
        assert "public.summary" in result.downstream

    async def test_get_lineage_returns_empty_for_unknown(self) -> None:
        """Test get_lineage returns empty context for unknown datasets."""
        client = MockLineageClient()

        result = await client.get_lineage("unknown.table")

        assert result.target == "unknown.table"
        assert result.upstream == ()
        assert result.downstream == ()
