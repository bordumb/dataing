"""Integration tests for lineage adapter integration with the investigation engine."""

import pytest

from dataing.adapters.context import ContextEngine
from dataing.adapters.lineage import (
    BaseLineageAdapter,
    DatasetId,
    Dataset,
    DatasetType,
    LineageCapabilities,
    LineageGraph,
    LineageProviderInfo,
    LineageProviderType,
    get_lineage_registry,
)
from dataing.core.domain_types import AnomalyAlert, LineageContext


class MockLineageAdapter(BaseLineageAdapter):
    """Mock lineage adapter for testing."""

    def __init__(self, lineage_data: dict[str, tuple[list[str], list[str]]] | None = None) -> None:
        """Initialize mock adapter.

        Args:
            lineage_data: Map of dataset name to (upstream, downstream) tuples.
        """
        super().__init__(config={})
        self._capabilities = LineageCapabilities(
            supports_column_lineage=False,
            supports_job_runs=False,
            supports_freshness=False,
            supports_search=False,
            supports_owners=False,
            supports_tags=False,
            max_upstream_depth=10,
            max_downstream_depth=10,
            is_realtime=False,
        )
        self._provider_info = LineageProviderInfo(
            provider=LineageProviderType.STATIC_SQL,
            display_name="Mock Lineage",
            description="Mock adapter for testing",
            capabilities=self._capabilities,
        )
        self.lineage_data = lineage_data or {}

    @property
    def capabilities(self) -> LineageCapabilities:
        """Get provider capabilities."""
        return self._capabilities

    @property
    def provider_info(self) -> LineageProviderInfo:
        """Get provider info."""
        return self._provider_info

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get mock dataset."""
        if dataset_id.name in self.lineage_data:
            return Dataset(
                id=dataset_id,
                name=dataset_id.name,
                qualified_name=dataset_id.name,
                dataset_type=DatasetType.TABLE,
                platform=dataset_id.platform,
            )
        return None

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get mock upstream datasets."""
        if dataset_id.name not in self.lineage_data:
            return []

        upstream_names, _ = self.lineage_data[dataset_id.name]
        return [
            Dataset(
                id=DatasetId(platform=dataset_id.platform, name=name),
                name=name,
                qualified_name=name,
                dataset_type=DatasetType.TABLE,
                platform=dataset_id.platform,
            )
            for name in upstream_names
        ]

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get mock downstream datasets."""
        if dataset_id.name not in self.lineage_data:
            return []

        _, downstream_names = self.lineage_data[dataset_id.name]
        return [
            Dataset(
                id=DatasetId(platform=dataset_id.platform, name=name),
                name=name,
                qualified_name=name,
                dataset_type=DatasetType.TABLE,
                platform=dataset_id.platform,
            )
            for name in downstream_names
        ]

    async def get_lineage_graph(
        self,
        dataset_id: DatasetId,
        upstream_depth: int = 3,
        downstream_depth: int = 3,
    ) -> LineageGraph:
        """Get mock lineage graph."""
        return LineageGraph(
            root=dataset_id,
            datasets={},
            edges=[],
        )


class TestContextEngineWithLineageAdapter:
    """Tests for ContextEngine with LineageAdapter integration."""

    @pytest.fixture
    def mock_lineage_adapter(self) -> MockLineageAdapter:
        """Create a mock lineage adapter with test data."""
        return MockLineageAdapter(
            lineage_data={
                "analytics.orders": (
                    ["raw.orders", "raw.customers"],  # upstream
                    ["analytics.revenue_report"],  # downstream
                ),
                "raw.orders": (
                    [],  # no upstream (source table)
                    ["analytics.orders"],  # downstream
                ),
            }
        )

    @pytest.fixture
    def context_engine(self, mock_lineage_adapter: MockLineageAdapter) -> ContextEngine:
        """Create a context engine with the mock lineage adapter."""
        return ContextEngine(lineage_adapter=mock_lineage_adapter)

    async def test_fetch_lineage_returns_context(
        self, context_engine: ContextEngine
    ) -> None:
        """Test that _fetch_lineage returns proper LineageContext."""
        lineage = await context_engine._fetch_lineage("analytics.orders")

        assert isinstance(lineage, LineageContext)
        assert lineage.target == "analytics.orders"
        assert "raw.orders" in lineage.upstream
        assert "raw.customers" in lineage.upstream
        assert "analytics.revenue_report" in lineage.downstream

    async def test_fetch_lineage_empty_for_unknown_dataset(
        self, context_engine: ContextEngine
    ) -> None:
        """Test that _fetch_lineage returns empty for unknown dataset."""
        lineage = await context_engine._fetch_lineage("unknown.table")

        assert isinstance(lineage, LineageContext)
        assert lineage.target == "unknown.table"
        assert len(lineage.upstream) == 0
        assert len(lineage.downstream) == 0

    async def test_fetch_lineage_source_table_no_upstream(
        self, context_engine: ContextEngine
    ) -> None:
        """Test that source tables have no upstream."""
        lineage = await context_engine._fetch_lineage("raw.orders")

        assert isinstance(lineage, LineageContext)
        assert lineage.target == "raw.orders"
        assert len(lineage.upstream) == 0
        assert "analytics.orders" in lineage.downstream

    def test_parse_dataset_id_simple(self, context_engine: ContextEngine) -> None:
        """Test parsing simple dataset ID."""
        dataset_id = context_engine._parse_dataset_id("analytics.orders")

        assert dataset_id.platform == "unknown"
        assert dataset_id.name == "analytics.orders"

    def test_parse_dataset_id_with_platform(self, context_engine: ContextEngine) -> None:
        """Test parsing dataset ID with platform prefix."""
        dataset_id = context_engine._parse_dataset_id("snowflake://db.schema.table")

        assert dataset_id.platform == "snowflake"
        assert dataset_id.name == "db.schema.table"


class TestLineageRegistry:
    """Tests for the lineage adapter registry."""

    def test_registry_singleton(self) -> None:
        """Test that get_lineage_registry returns the same instance."""
        registry1 = get_lineage_registry()
        registry2 = get_lineage_registry()

        assert registry1 is registry2

    def test_registry_has_expected_providers(self) -> None:
        """Test that registry has all expected providers."""
        registry = get_lineage_registry()
        providers = registry.list_providers()

        provider_types = {p.provider_type for p in providers}

        assert LineageProviderType.DBT in provider_types
        assert LineageProviderType.OPENLINEAGE in provider_types
        assert LineageProviderType.AIRFLOW in provider_types

    def test_create_dbt_adapter(self) -> None:
        """Test creating a dbt adapter."""
        registry = get_lineage_registry()

        adapter = registry.create(
            "dbt",
            {
                "manifest_path": "/tmp/manifest.json",
                "target_platform": "snowflake",
            },
        )

        assert adapter is not None
        assert adapter.provider_info.provider == LineageProviderType.DBT

    def test_create_composite_adapter(self) -> None:
        """Test creating a composite adapter."""
        registry = get_lineage_registry()

        adapter = registry.create_composite([
            {"provider": "dbt", "priority": 10, "config": {"manifest_path": "/tmp/m.json"}},
            {"provider": "openlineage", "priority": 5, "config": {"base_url": "http://localhost:5000"}},
        ])

        assert adapter is not None
        # Composite adapter has multiple providers


class TestDatasetId:
    """Tests for DatasetId parsing and formatting."""

    def test_from_simple_name(self) -> None:
        """Test parsing a simple table name."""
        ds = DatasetId.from_urn("my_table")

        assert ds.platform == "unknown"
        assert ds.name == "my_table"

    def test_from_platform_url(self) -> None:
        """Test parsing platform://name format."""
        ds = DatasetId.from_urn("postgres://mydb.public.users")

        assert ds.platform == "postgres"
        assert ds.name == "mydb.public.users"

    def test_from_datahub_urn(self) -> None:
        """Test parsing DataHub URN format."""
        ds = DatasetId.from_urn(
            "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.public.orders,PROD)"
        )

        assert ds.platform == "snowflake"
        assert "orders" in ds.name.lower()

    def test_str_representation(self) -> None:
        """Test string representation of DatasetId."""
        ds = DatasetId(platform="snowflake", name="db.schema.table")

        assert str(ds) == "snowflake://db.schema.table"
