"""Tests for SDK types."""

import pytest

from dataing_sdk import (
    AssetRef,
    DataingClient,
    EvidenceKind,
    RunStatus,
    TERMINAL_STATUSES,
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
        asset = AssetRef.from_urn(
            "snowflake://db.schema.table", datasource_id="ds-123"
        )
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
