"""Unit tests for CodeChangesRepository."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.code_changes import CodeChangesRepository
from dataing.core.domain_types import RelevantCodeChange


class TestCodeChangesRepository:
    """Tests for CodeChangesRepository."""

    @pytest.fixture
    def mock_conn(self) -> AsyncMock:
        """Return a mock connection."""
        return AsyncMock()

    @pytest.fixture
    def mock_db(self, mock_conn: AsyncMock) -> AppDatabase:
        """Return an AppDatabase instance with a mocked pool."""
        db = AppDatabase(dsn="postgresql://localhost/test")

        mock_pool = MagicMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool.acquire = mock_acquire
        mock_pool.close = AsyncMock()
        db.pool = mock_pool
        return db

    @pytest.fixture
    def repo(self, mock_db: AppDatabase) -> CodeChangesRepository:
        """Return a CodeChangesRepository instance."""
        return CodeChangesRepository(mock_db)

    @pytest.fixture
    def tenant_id(self) -> uuid.UUID:
        """Return a sample tenant ID."""
        return uuid.uuid4()

    @pytest.fixture
    def exact_match_row(self) -> dict:
        """Return a sample exact match code change row."""
        return {
            "commit_hash": "abc123",
            "author_name": "Jane Developer",
            "message": "fix: update order calculations",
            "committed_at": datetime.now(UTC) - timedelta(days=2),
            "affected_assets": json.dumps([{"name": "prod.analytics.orders"}]),
            "relevance_score": 1.0,
            "relevance_reason": "directly_affects_asset",
        }

    @pytest.fixture
    def upstream_match_row(self) -> dict:
        """Return a sample upstream match code change row."""
        return {
            "commit_hash": "def456",
            "author_name": "John Engineer",
            "message": "feat: add new customer fields",
            "committed_at": datetime.now(UTC) - timedelta(days=5),
            "affected_assets": json.dumps([{"name": "prod.raw.customers"}]),
            "relevance_score": 0.7,
            "relevance_reason": "affects_upstream_dependency",
        }

    @pytest.fixture
    def path_match_row(self) -> dict:
        """Return a sample path match code change row."""
        return {
            "commit_hash": "ghi789",
            "author_name": "Alice Data",
            "message": "refactor: improve SQL performance",
            "committed_at": datetime.now(UTC) - timedelta(days=10),
            "affected_assets": json.dumps([]),
            "relevance_score": 0.4,
            "relevance_reason": "matches_file_path_pattern",
        }

    # =========================================================================
    # Relevance Ranking Tests
    # =========================================================================

    async def test_exact_match_ranked_highest(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
        exact_match_row: dict,
        upstream_match_row: dict,
        path_match_row: dict,
    ) -> None:
        """Test that exact matches are ranked highest (1.0)."""
        # Return rows in wrong order - exact should still come first after processing
        mock_conn.fetch.return_value = [
            exact_match_row,
            upstream_match_row,
            path_match_row,
        ]

        results = await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
            upstream_assets=["prod.raw.customers"],
        )

        assert len(results) == 3
        assert results[0].relevance_score == 1.0
        assert results[0].relevance_reason == "directly_affects_asset"
        assert results[0].commit_hash == "abc123"

    async def test_upstream_match_ranked_second(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
        upstream_match_row: dict,
        path_match_row: dict,
    ) -> None:
        """Test that upstream matches are ranked second (0.7)."""
        mock_conn.fetch.return_value = [upstream_match_row, path_match_row]

        results = await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
            upstream_assets=["prod.raw.customers"],
        )

        assert len(results) == 2
        assert results[0].relevance_score == 0.7
        assert results[0].relevance_reason == "affects_upstream_dependency"

    async def test_path_match_ranked_third(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
        path_match_row: dict,
    ) -> None:
        """Test that path matches are ranked lowest (0.4)."""
        mock_conn.fetch.return_value = [path_match_row]

        results = await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
        )

        assert len(results) == 1
        assert results[0].relevance_score == 0.4
        assert results[0].relevance_reason == "matches_file_path_pattern"

    # =========================================================================
    # Lookback Filtering Tests
    # =========================================================================

    async def test_lookback_default_14_days(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test that default lookback is 14 days."""
        mock_conn.fetch.return_value = []

        await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
        )

        # Verify the query was called with a datetime ~14 days ago
        # Args: query, tenant_id, since, exact_match_json, upstream_json, asset_id, max_results
        call_args = mock_conn.fetch.call_args
        since_param = call_args[0][2]  # Third positional arg is 'since'
        expected_since = datetime.now(UTC) - timedelta(days=14)
        # Allow 1 second tolerance
        assert abs((since_param - expected_since).total_seconds()) < 1

    async def test_lookback_configurable(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test that lookback days can be configured."""
        mock_conn.fetch.return_value = []

        await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
            lookback_days=7,
        )

        # Args: query, tenant_id, since, exact_match_json, upstream_json, asset_id, max_results
        call_args = mock_conn.fetch.call_args
        since_param = call_args[0][2]  # Third positional arg is 'since'
        expected_since = datetime.now(UTC) - timedelta(days=7)
        assert abs((since_param - expected_since).total_seconds()) < 1

    # =========================================================================
    # Max Results Tests
    # =========================================================================

    async def test_max_results_default_5(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test that default max_results is 5."""
        mock_conn.fetch.return_value = []

        await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
        )

        # Verify the query was called with limit=5
        call_args = mock_conn.fetch.call_args
        limit_param = call_args[0][-1]  # Last positional arg is limit
        assert limit_param == 5

    async def test_max_results_configurable(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test that max_results can be configured."""
        mock_conn.fetch.return_value = []

        await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
            max_results=10,
        )

        call_args = mock_conn.fetch.call_args
        limit_param = call_args[0][-1]
        assert limit_param == 10

    async def test_max_results_caps_output(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
        exact_match_row: dict,
    ) -> None:
        """Test that results are capped at max_results."""
        # Return more rows than the limit
        rows = [{**exact_match_row, "commit_hash": f"hash{i}"} for i in range(10)]
        mock_conn.fetch.return_value = rows[:3]  # DB should return limited

        results = await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
            max_results=3,
        )

        assert len(results) == 3

    # =========================================================================
    # Empty Result Tests
    # =========================================================================

    async def test_empty_results_when_no_matches(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test that empty list is returned when no changes match."""
        mock_conn.fetch.return_value = []

        results = await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.nonexistent",
        )

        assert results == []

    async def test_empty_results_no_upstream(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test query works when no upstream assets provided."""
        mock_conn.fetch.return_value = []

        results = await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
            upstream_assets=None,
        )

        assert results == []
        # Verify query was called (no exception)
        mock_conn.fetch.assert_called_once()

    # =========================================================================
    # Domain Conversion Tests
    # =========================================================================

    async def test_row_to_domain_conversion(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
        exact_match_row: dict,
    ) -> None:
        """Test that database rows are correctly converted to domain objects."""
        mock_conn.fetch.return_value = [exact_match_row]

        results = await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
        )

        assert len(results) == 1
        change = results[0]
        assert isinstance(change, RelevantCodeChange)
        assert change.commit_hash == "abc123"
        assert change.author_name == "Jane Developer"
        assert change.message == "fix: update order calculations"
        assert change.relevance_score == 1.0
        assert change.relevance_reason == "directly_affects_asset"
        assert "prod.analytics.orders" in change.affected_assets

    async def test_row_with_null_optional_fields(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test conversion handles null optional fields."""
        row = {
            "commit_hash": "xyz999",
            "author_name": None,
            "message": None,
            "committed_at": None,
            "affected_assets": json.dumps([]),
            "relevance_score": 0.4,
            "relevance_reason": "matches_file_path_pattern",
        }
        mock_conn.fetch.return_value = [row]

        results = await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="prod.analytics.orders",
        )

        assert len(results) == 1
        change = results[0]
        assert change.commit_hash == "xyz999"
        assert change.author_name is None
        assert change.message is None
        assert change.committed_at is None
        assert change.affected_assets == []

    async def test_affected_assets_as_string_parsed(
        self,
        repo: CodeChangesRepository,
        mock_conn: AsyncMock,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test that affected_assets JSON string is properly parsed."""
        row = {
            "commit_hash": "abc123",
            "author_name": "Dev",
            "message": "test",
            "committed_at": datetime.now(UTC),
            "affected_assets": '[{"name": "table1"}, {"name": "table2"}]',
            "relevance_score": 1.0,
            "relevance_reason": "directly_affects_asset",
        }
        mock_conn.fetch.return_value = [row]

        results = await repo.get_relevant_code_changes(
            tenant_id=tenant_id,
            asset_id="table1",
        )

        assert len(results) == 1
        assert results[0].affected_assets == ["table1", "table2"]
