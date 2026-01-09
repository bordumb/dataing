"""Unit tests for DefaultContextEngine."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from dataing.adapters.context.engine import DefaultContextEngine
from dataing.core.domain_types import (
    AnomalyAlert,
    LineageContext,
    SchemaContext,
    TableSchema,
)
from dataing.core.exceptions import SchemaDiscoveryError


class TestDefaultContextEngine:
    """Tests for DefaultContextEngine."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database adapter."""
        mock = AsyncMock()
        mock.get_schema.return_value = SchemaContext(
            tables=(
                TableSchema(
                    table_name="public.orders",
                    columns=("id", "user_id", "total"),
                    column_types={"id": "integer", "user_id": "integer", "total": "numeric"},
                ),
            )
        )
        return mock

    @pytest.fixture
    def mock_lineage_client(self) -> AsyncMock:
        """Return a mock lineage client."""
        mock = AsyncMock()
        mock.get_lineage.return_value = LineageContext(
            target="public.orders",
            upstream=("public.users",),
            downstream=(),
        )
        return mock

    @pytest.fixture
    def alert(self) -> AnomalyAlert:
        """Return a sample anomaly alert."""
        return AnomalyAlert(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
            severity="high",
        )

    async def test_gather_returns_context_with_schema(
        self,
        mock_db: AsyncMock,
        alert: AnomalyAlert,
    ) -> None:
        """Test that gather returns context with schema."""
        engine = DefaultContextEngine(db=mock_db)

        context = await engine.gather(alert)

        assert context.schema is not None
        assert len(context.schema.tables) == 1
        assert context.schema.tables[0].table_name == "public.orders"
        mock_db.get_schema.assert_called_once()

    async def test_gather_returns_context_with_lineage(
        self,
        mock_db: AsyncMock,
        mock_lineage_client: AsyncMock,
        alert: AnomalyAlert,
    ) -> None:
        """Test that gather returns context with lineage when client provided."""
        engine = DefaultContextEngine(db=mock_db, lineage_client=mock_lineage_client)

        context = await engine.gather(alert)

        assert context.lineage is not None
        assert context.lineage.target == "public.orders"
        assert "public.users" in context.lineage.upstream
        mock_lineage_client.get_lineage.assert_called_once_with("public.orders")

    async def test_gather_raises_on_empty_schema(
        self,
        mock_db: AsyncMock,
        alert: AnomalyAlert,
    ) -> None:
        """Test that gather raises SchemaDiscoveryError on empty schema."""
        mock_db.get_schema.return_value = SchemaContext(tables=())
        engine = DefaultContextEngine(db=mock_db)

        with pytest.raises(SchemaDiscoveryError) as exc_info:
            await engine.gather(alert)

        assert "No tables discovered" in str(exc_info.value)

    async def test_gather_raises_on_schema_error(
        self,
        mock_db: AsyncMock,
        alert: AnomalyAlert,
    ) -> None:
        """Test that gather raises SchemaDiscoveryError on database error."""
        mock_db.get_schema.side_effect = Exception("Database connection failed")
        engine = DefaultContextEngine(db=mock_db)

        with pytest.raises(SchemaDiscoveryError) as exc_info:
            await engine.gather(alert)

        assert "Failed to discover schema" in str(exc_info.value)

    async def test_gather_continues_on_lineage_error(
        self,
        mock_db: AsyncMock,
        mock_lineage_client: AsyncMock,
        alert: AnomalyAlert,
    ) -> None:
        """Test that gather continues if lineage discovery fails."""
        mock_lineage_client.get_lineage.side_effect = Exception("Lineage API error")
        engine = DefaultContextEngine(db=mock_db, lineage_client=mock_lineage_client)

        context = await engine.gather(alert)

        # Should still return valid context with schema, just no lineage
        assert context.schema is not None
        assert context.lineage is None
