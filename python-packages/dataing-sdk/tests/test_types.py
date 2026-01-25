"""Tests for SDK types."""

import pytest
from dataing_sdk import (
    TERMINAL_STATUSES,
    AssetRef,
    ColumnSchema,
    ConnectionTestResult,
    DataingClient,
    Datasource,
    DatasourceSchema,
    DiffResult,
    EvidenceKind,
    ExplainResult,
    QueryResult,
    RunStatus,
    TableSchema,
)


class TestAssetRef:
    """Tests for AssetRef."""

    def test_to_urn_simple(self) -> None:
        """Test URN generation."""
        asset = AssetRef(platform="postgres", name="ecommerce.public.orders")
        assert asset.to_urn() == "postgres://ecommerce.public.orders"

    def test_from_urn_simple(self) -> None:
        """Test parsing simple URN format."""
        asset = AssetRef.from_urn("postgres://ecommerce.public.orders")
        assert asset.platform == "postgres"
        assert asset.name == "ecommerce.public.orders"
        assert asset.datasource_id is None

    def test_from_urn_with_datasource(self) -> None:
        """Test parsing URN with datasource_id."""
        asset = AssetRef.from_urn("snowflake://db.schema.table", datasource_id="ds-123")
        assert asset.platform == "snowflake"
        assert asset.name == "db.schema.table"
        assert asset.datasource_id == "ds-123"

    def test_from_urn_datahub_format(self) -> None:
        """Test parsing DataHub URN format."""
        urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,db.schema.table,PROD)"
        asset = AssetRef.from_urn(urn)
        assert asset.platform == "snowflake"
        assert asset.name == "db.schema.table"

    def test_roundtrip(self) -> None:
        """Test URN roundtrip."""
        original = AssetRef(
            platform="postgres",
            name="analytics.public.orders",
            datasource_id="ds-456",
        )
        urn = original.to_urn()
        parsed = AssetRef.from_urn(urn, datasource_id=original.datasource_id)
        assert parsed == original

    def test_invalid_urn_raises(self) -> None:
        """Test that invalid URN raises ValueError."""
        with pytest.raises(ValueError, match="Invalid URN format"):
            AssetRef.from_urn("invalid-urn-no-protocol")

    def test_hashable(self) -> None:
        """Test that AssetRef is hashable for use in sets."""
        a1 = AssetRef(platform="postgres", name="db.schema.table")
        a2 = AssetRef(platform="postgres", name="db.schema.table")
        a3 = AssetRef(platform="snowflake", name="db.schema.table")

        asset_set = {a1, a2, a3}
        assert len(asset_set) == 2  # a1 and a2 are equal


class TestEnums:
    """Tests for enums."""

    def test_run_status_values(self) -> None:
        """Test RunStatus enum values."""
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.FAILED == "failed"
        assert RunStatus.CANCELLED == "cancelled"

    def test_terminal_statuses(self) -> None:
        """Test TERMINAL_STATUSES contains correct values."""
        assert RunStatus.COMPLETED in TERMINAL_STATUSES
        assert RunStatus.FAILED in TERMINAL_STATUSES
        assert RunStatus.CANCELLED in TERMINAL_STATUSES
        assert RunStatus.RUNNING not in TERMINAL_STATUSES

    def test_evidence_kind_values(self) -> None:
        """Test EvidenceKind enum values."""
        assert EvidenceKind.SQL == "sql"
        assert EvidenceKind.LOG == "log"
        assert EvidenceKind.METRIC == "metric"
        assert EvidenceKind.SCHEMA == "schema"
        assert EvidenceKind.PIPELINE == "pipeline"
        assert EvidenceKind.NOTE == "note"


class TestDataingClient:
    """Tests for DataingClient."""

    def test_client_init(self) -> None:
        """Test client initialization."""
        client = DataingClient(
            base_url="https://api.example.com",
            api_key="test-key",
            timeout=60.0,
        )
        assert client.base_url == "https://api.example.com"
        assert client.api_key == "test-key"
        assert client.timeout == 60.0

    def test_client_strips_trailing_slash(self) -> None:
        """Test that base_url trailing slash is stripped."""
        client = DataingClient(base_url="https://api.example.com/")
        assert client.base_url == "https://api.example.com"

    def test_client_default_values(self) -> None:
        """Test client default values."""
        client = DataingClient()
        assert client.base_url == "http://localhost:8000"
        assert client.api_key is None
        assert client.timeout == 30.0


class TestResultTypes:
    """Tests for result types (QueryResult, DiffResult, ExplainResult)."""

    def test_query_result_default_values(self) -> None:
        """Test QueryResult default values."""
        result = QueryResult(
            columns=[{"name": "id", "type": "int"}],
            rows=[{"id": 1}],
            row_count=1,
        )
        assert result.truncated is False
        assert result.execution_time_ms is None

    def test_query_result_all_values(self) -> None:
        """Test QueryResult with all values."""
        result = QueryResult(
            columns=[{"name": "id", "type": "int"}, {"name": "name", "type": "str"}],
            rows=[{"id": 1, "name": "test"}],
            row_count=1,
            truncated=True,
            execution_time_ms=42,
        )
        assert len(result.columns) == 2
        assert len(result.rows) == 1
        assert result.row_count == 1
        assert result.truncated is True
        assert result.execution_time_ms == 42

    def test_diff_result_default_values(self) -> None:
        """Test DiffResult default values."""
        result = DiffResult(
            metric="row_count",
            window="7d",
        )
        assert result.current_value is None
        assert result.previous_value is None
        assert result.delta is None
        assert result.delta_percent is None
        assert result.trend is None
        assert result.samples == []

    def test_diff_result_all_values(self) -> None:
        """Test DiffResult with all values."""
        result = DiffResult(
            metric="row_count",
            window="7d",
            current_value=1000.0,
            previous_value=900.0,
            delta=100.0,
            delta_percent=11.1,
            trend="up",
            samples=[{"timestamp": "2024-01-01", "value": 900}],
        )
        assert result.current_value == 1000.0
        assert result.previous_value == 900.0
        assert result.delta == 100.0
        assert result.delta_percent == 11.1
        assert result.trend == "up"
        assert len(result.samples) == 1

    def test_explain_result_required_fields(self) -> None:
        """Test ExplainResult requires summary."""
        result = ExplainResult(summary="Test summary")
        assert result.summary == "Test summary"
        assert result.insights == []
        assert result.recommendations == []
        assert result.related_assets == []

    def test_explain_result_all_values(self) -> None:
        """Test ExplainResult with all values."""
        result = ExplainResult(
            summary="Data quality issues detected",
            insights=["High null rate in column X", "Volume drop detected"],
            recommendations=["Investigate data pipeline", "Add validation"],
            related_assets=["postgres://db.schema.table1", "postgres://db.schema.table2"],
        )
        assert result.summary == "Data quality issues detected"
        assert len(result.insights) == 2
        assert len(result.recommendations) == 2
        assert len(result.related_assets) == 2


class TestDatasourceTypes:
    """Tests for Datasource-related types."""

    def test_datasource_required_fields(self) -> None:
        """Test Datasource with required fields."""
        ds = Datasource(
            id="ds-abc123",
            name="Production Postgres",
            source_type="postgres",
        )
        assert ds.id == "ds-abc123"
        assert ds.name == "Production Postgres"
        assert ds.source_type == "postgres"
        assert ds.status is None

    def test_datasource_all_fields(self) -> None:
        """Test Datasource with all fields."""
        ds = Datasource(
            id="ds-abc123",
            name="Production Postgres",
            source_type="postgres",
            status="connected",
        )
        assert ds.status == "connected"

    def test_datasource_from_backend_response(self) -> None:
        """Test Datasource parses backend response with 'type' field."""
        # Backend API returns 'type' but SDK uses 'source_type'
        backend_data = {
            "id": "ds-abc123",
            "name": "Production Postgres",
            "type": "postgres",
            "status": "connected",
        }
        ds = Datasource.model_validate(backend_data)
        assert ds.id == "ds-abc123"
        assert ds.source_type == "postgres"  # Mapped from 'type'
        assert ds.status == "connected"

    def test_test_connection_result_success(self) -> None:
        """Test ConnectionTestResult for success case."""
        result = ConnectionTestResult(success=True, latency_ms=42)
        assert result.success is True
        assert result.latency_ms == 42
        assert result.error is None

    def test_test_connection_result_failure(self) -> None:
        """Test ConnectionTestResult for failure case."""
        result = ConnectionTestResult(success=False, error="Connection refused")
        assert result.success is False
        assert result.latency_ms is None
        assert result.error == "Connection refused"

    def test_test_connection_result_from_backend(self) -> None:
        """Test ConnectionTestResult parses backend response with 'message' field."""
        # Backend API returns 'message' but SDK uses 'error'
        backend_data = {
            "success": False,
            "message": "Connection refused",
            "latency_ms": None,
        }
        result = ConnectionTestResult.model_validate(backend_data)
        assert result.success is False
        assert result.error == "Connection refused"  # Mapped from 'message'

    def test_column_schema(self) -> None:
        """Test ColumnSchema."""
        col = ColumnSchema(name="id", data_type="INTEGER", nullable=False)
        assert col.name == "id"
        assert col.data_type == "INTEGER"
        assert col.nullable is False

    def test_column_schema_defaults(self) -> None:
        """Test ColumnSchema default values."""
        col = ColumnSchema(name="name", data_type="VARCHAR")
        assert col.nullable is True

    def test_table_schema(self) -> None:
        """Test TableSchema."""
        table = TableSchema(
            name="public.orders",
            columns=[
                ColumnSchema(name="id", data_type="INTEGER", nullable=False),
                ColumnSchema(name="customer_id", data_type="INTEGER"),
            ],
        )
        assert table.name == "public.orders"
        assert len(table.columns) == 2
        assert table.columns[0].name == "id"

    def test_datasource_schema(self) -> None:
        """Test DatasourceSchema."""
        schema = DatasourceSchema(
            tables=[
                TableSchema(
                    name="public.orders",
                    columns=[
                        ColumnSchema(name="id", data_type="INTEGER"),
                    ],
                ),
                TableSchema(
                    name="public.customers",
                    columns=[
                        ColumnSchema(name="id", data_type="INTEGER"),
                        ColumnSchema(name="email", data_type="VARCHAR"),
                    ],
                ),
            ]
        )
        assert len(schema.tables) == 2
        assert schema.tables[0].name == "public.orders"
        assert len(schema.tables[1].columns) == 2
