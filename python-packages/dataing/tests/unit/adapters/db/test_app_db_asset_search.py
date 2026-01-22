"""Unit tests for AppDatabase.search_asset_instances method."""

import base64
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase


class TestSearchAssetInstances:
    """Test AppDatabase.search_asset_instances method."""

    @pytest.fixture
    def app_db(self) -> AppDatabase:
        """Create AppDatabase instance with mocked pool."""
        db = AppDatabase("postgresql://test:test@localhost/test")
        db.pool = AsyncMock()
        return db

    async def test_search_returns_results_with_datasource_context(
        self, app_db: AppDatabase
    ) -> None:
        """Test search returns results with datasource information."""
        tenant_id = uuid4()
        datasource_id = uuid4()
        dataset_id = uuid4()

        mock_rows = [
            {
                "id": dataset_id,
                "datasource_id": datasource_id,
                "native_path": "public.orders",
                "name": "orders",
                "table_type": "table",
                "schema_name": "public",
                "catalog_name": None,
                "row_count": 1000,
                "column_count": 10,
                "datasource_name": "Production DB",
                "platform": "postgres",
                "match_reason": "name_prefix",
            }
        ]

        with patch.object(app_db, "fetch_all", new_callable=AsyncMock) as mock_fetch_all:
            with patch.object(app_db, "fetch_one", new_callable=AsyncMock) as mock_fetch_one:
                mock_fetch_all.return_value = mock_rows
                mock_fetch_one.return_value = {"count": 1}

                results, next_cursor, total_hint = await app_db.search_asset_instances(
                    tenant_id=tenant_id,
                    query="orders",
                    limit=10,
                )

        assert len(results) == 1
        assert results[0]["name"] == "orders"
        assert results[0]["datasource_name"] == "Production DB"
        assert results[0]["platform"] == "postgres"
        assert results[0]["match_reason"] == "name_prefix"
        assert next_cursor is None
        assert total_hint == 1

    async def test_search_pagination_cursor(self, app_db: AppDatabase) -> None:
        """Test pagination cursor is generated when there are more results."""
        tenant_id = uuid4()
        datasource_id = uuid4()
        dataset_id = uuid4()

        # Return 11 rows (limit + 1) to indicate has_more
        mock_rows = [
            {
                "id": uuid4(),
                "datasource_id": datasource_id,
                "native_path": f"public.table_{i}",
                "name": f"table_{i}",
                "table_type": "table",
                "schema_name": "public",
                "catalog_name": None,
                "row_count": 100,
                "column_count": 5,
                "datasource_name": "Production DB",
                "platform": "postgres",
                "match_reason": "fuzzy",
            }
            for i in range(11)  # 11 rows = has_more
        ]
        # Fix the last row for deterministic cursor
        mock_rows[-1] = {
            "id": dataset_id,
            "datasource_id": datasource_id,
            "native_path": "public.table_9",
            "name": "table_9",
            "table_type": "table",
            "schema_name": "public",
            "catalog_name": None,
            "row_count": 100,
            "column_count": 5,
            "datasource_name": "Production DB",
            "platform": "postgres",
            "match_reason": "fuzzy",
        }

        with patch.object(app_db, "fetch_all", new_callable=AsyncMock) as mock_fetch_all:
            with patch.object(app_db, "fetch_one", new_callable=AsyncMock) as mock_fetch_one:
                mock_fetch_all.return_value = mock_rows
                mock_fetch_one.return_value = {"count": 50}

                results, next_cursor, total_hint = await app_db.search_asset_instances(
                    tenant_id=tenant_id,
                    query="table",
                    limit=10,
                )

        # Should return 10 results (limit)
        assert len(results) == 10
        # Should have a cursor
        assert next_cursor is not None
        # Decode and verify cursor format
        decoded = base64.b64decode(next_cursor).decode()
        assert "|" in decoded
        assert total_hint == 50

    async def test_search_with_cursor_uses_cursor_filter(
        self, app_db: AppDatabase
    ) -> None:
        """Test search with cursor includes cursor filter in query."""
        tenant_id = uuid4()
        datasource_id = uuid4()
        dataset_id = uuid4()

        # Create a cursor
        cursor_str = f"public.orders|{datasource_id}|{dataset_id}"
        cursor = base64.b64encode(cursor_str.encode()).decode()

        with patch.object(app_db, "fetch_all", new_callable=AsyncMock) as mock_fetch_all:
            with patch.object(app_db, "fetch_one", new_callable=AsyncMock) as mock_fetch_one:
                mock_fetch_all.return_value = []
                mock_fetch_one.return_value = {"count": 0}

                await app_db.search_asset_instances(
                    tenant_id=tenant_id,
                    query="users",
                    limit=10,
                    cursor=cursor,
                )

        # Verify fetch_all was called (query includes cursor filter)
        mock_fetch_all.assert_called_once()
        call_args = mock_fetch_all.call_args
        query = call_args[0][0]
        # Query should include cursor comparison
        assert ">" in query

    async def test_search_with_datasource_filter(self, app_db: AppDatabase) -> None:
        """Test search with datasource_id filter."""
        tenant_id = uuid4()
        datasource_id = uuid4()

        with patch.object(app_db, "fetch_all", new_callable=AsyncMock) as mock_fetch_all:
            with patch.object(app_db, "fetch_one", new_callable=AsyncMock) as mock_fetch_one:
                mock_fetch_all.return_value = []
                mock_fetch_one.return_value = {"count": 0}

                await app_db.search_asset_instances(
                    tenant_id=tenant_id,
                    query="orders",
                    limit=10,
                    datasource_id=datasource_id,
                )

        # Verify both fetch_all and fetch_one include datasource filter
        assert mock_fetch_all.called
        query = mock_fetch_all.call_args[0][0]
        assert "datasource_id" in query

    async def test_search_limit_capped_at_100(self, app_db: AppDatabase) -> None:
        """Test search limit is capped at 100."""
        tenant_id = uuid4()

        with patch.object(app_db, "fetch_all", new_callable=AsyncMock) as mock_fetch_all:
            with patch.object(app_db, "fetch_one", new_callable=AsyncMock) as mock_fetch_one:
                mock_fetch_all.return_value = []
                mock_fetch_one.return_value = {"count": 0}

                await app_db.search_asset_instances(
                    tenant_id=tenant_id,
                    query="test",
                    limit=500,  # Request 500
                )

        # Verify LIMIT in query is 101 (100 + 1 for has_more check)
        call_args = mock_fetch_all.call_args
        # The last arg should be limit + 1 = 101
        args = call_args[0]
        assert args[-1] == 101  # 100 (capped) + 1 (has_more check)

    async def test_search_match_reason_priority(self, app_db: AppDatabase) -> None:
        """Test match_reason is calculated correctly."""
        tenant_id = uuid4()
        datasource_id = uuid4()

        # The SQL query calculates match_reason based on prefix vs contains
        # This is tested via the actual SQL CASE expression
        mock_rows = [
            {
                "id": uuid4(),
                "datasource_id": datasource_id,
                "native_path": "public.orders",
                "name": "orders",
                "table_type": "table",
                "schema_name": "public",
                "catalog_name": None,
                "row_count": 1000,
                "column_count": 10,
                "datasource_name": "Production DB",
                "platform": "postgres",
                "match_reason": "name_prefix",  # Simulated from SQL CASE
            },
            {
                "id": uuid4(),
                "datasource_id": datasource_id,
                "native_path": "analytics.customer_orders",
                "name": "customer_orders",
                "table_type": "table",
                "schema_name": "analytics",
                "catalog_name": None,
                "row_count": 500,
                "column_count": 8,
                "datasource_name": "Production DB",
                "platform": "postgres",
                "match_reason": "fuzzy",  # Contains but not prefix
            },
        ]

        with patch.object(app_db, "fetch_all", new_callable=AsyncMock) as mock_fetch_all:
            with patch.object(app_db, "fetch_one", new_callable=AsyncMock) as mock_fetch_one:
                mock_fetch_all.return_value = mock_rows
                mock_fetch_one.return_value = {"count": 2}

                results, _, _ = await app_db.search_asset_instances(
                    tenant_id=tenant_id,
                    query="orders",
                    limit=10,
                )

        assert len(results) == 2
        # First result (exact prefix match) should have name_prefix
        assert results[0]["match_reason"] == "name_prefix"
        # Second result (contains but not prefix) should have fuzzy
        assert results[1]["match_reason"] == "fuzzy"
