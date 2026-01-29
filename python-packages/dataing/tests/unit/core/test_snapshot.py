"""Unit tests for investigation snapshot models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from dataing.core.snapshot import (
    EnvironmentMetadata,
    InvestigationSnapshot,
    LineageSnapshot,
    SampleDataFormat,
    SampleDataReference,
    SnapshotCheckpoint,
)


class TestSnapshotCheckpoint:
    """Tests for SnapshotCheckpoint enum."""

    def test_all_checkpoints_defined(self) -> None:
        """Test that all expected checkpoints are defined."""
        assert SnapshotCheckpoint.START == "start"
        assert SnapshotCheckpoint.HYPOTHESIS_GENERATED == "hypothesis_generated"
        assert SnapshotCheckpoint.EVIDENCE_COLLECTED == "evidence_collected"
        assert SnapshotCheckpoint.COMPLETE == "complete"
        assert SnapshotCheckpoint.FAILED == "failed"


class TestSampleDataFormat:
    """Tests for SampleDataFormat enum."""

    def test_all_formats_defined(self) -> None:
        """Test that all expected formats are defined."""
        assert SampleDataFormat.PARQUET == "parquet"
        assert SampleDataFormat.JSON == "json"
        assert SampleDataFormat.REFERENCE == "reference"


class TestEnvironmentMetadata:
    """Tests for EnvironmentMetadata model."""

    def test_default_values(self) -> None:
        """Test that default values are populated."""
        env = EnvironmentMetadata()
        assert env.python_version is not None
        assert len(env.python_version) > 0
        assert env.platform is not None

    def test_capture_current(self) -> None:
        """Test capturing current environment."""
        env = EnvironmentMetadata.capture_current()
        assert env.python_version is not None
        assert env.platform in ["linux", "darwin", "win32"]
        assert isinstance(env.package_versions, dict)

    def test_custom_values(self) -> None:
        """Test setting custom values."""
        env = EnvironmentMetadata(
            python_version="3.11.0",
            platform="linux",
            dataing_version="1.0.0",
            datasource_type="postgresql",
            package_versions={"pydantic": "2.0.0"},
        )
        assert env.python_version == "3.11.0"
        assert env.platform == "linux"
        assert env.dataing_version == "1.0.0"
        assert env.datasource_type == "postgresql"
        assert env.package_versions["pydantic"] == "2.0.0"

    def test_frozen(self) -> None:
        """Test that model is immutable."""
        from pydantic import ValidationError

        env = EnvironmentMetadata()
        with pytest.raises(ValidationError):
            env.python_version = "3.12.0"  # type: ignore[misc]


class TestSampleDataReference:
    """Tests for SampleDataReference model."""

    def test_create_reference(self) -> None:
        """Test creating a sample data reference."""
        ref = SampleDataReference(
            table_name="analytics.orders",
            storage_path="s3://bucket/snapshots/orders.parquet",
            format=SampleDataFormat.PARQUET,
            row_count=5000,
            size_bytes=1024 * 1024,
            checksum="abc123",
        )
        assert ref.table_name == "analytics.orders"
        assert ref.storage_path == "s3://bucket/snapshots/orders.parquet"
        assert ref.format == SampleDataFormat.PARQUET
        assert ref.row_count == 5000
        assert ref.size_bytes == 1024 * 1024
        assert ref.checksum == "abc123"

    def test_optional_checksum(self) -> None:
        """Test that checksum is optional."""
        ref = SampleDataReference(
            table_name="orders",
            storage_path="/tmp/orders.json",
            format=SampleDataFormat.JSON,
            row_count=100,
            size_bytes=1024,
        )
        assert ref.checksum is None


class TestLineageSnapshot:
    """Tests for LineageSnapshot model."""

    def test_create_lineage_snapshot(self) -> None:
        """Test creating a lineage snapshot."""
        lineage = LineageSnapshot(
            target="analytics.orders",
            upstream=["raw.orders", "raw.customers"],
            downstream=["analytics.revenue", "analytics.customer_ltv"],
            depth=2,
        )
        assert lineage.target == "analytics.orders"
        assert len(lineage.upstream) == 2
        assert len(lineage.downstream) == 2
        assert lineage.depth == 2

    def test_empty_lineage(self) -> None:
        """Test lineage with no upstream/downstream."""
        lineage = LineageSnapshot(target="standalone_table")
        assert lineage.target == "standalone_table"
        assert lineage.upstream == []
        assert lineage.downstream == []

    def test_from_lineage_context_none(self) -> None:
        """Test from_lineage_context with None input."""
        result = LineageSnapshot.from_lineage_context(None)
        assert result is None


class TestInvestigationSnapshot:
    """Tests for InvestigationSnapshot model."""

    def test_create_minimal_snapshot(self) -> None:
        """Test creating a snapshot with minimal required fields."""
        snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.START,
        )
        assert snapshot.version == "1.0"
        assert snapshot.checkpoint == SnapshotCheckpoint.START
        assert snapshot.hypotheses == []
        assert snapshot.evidence == []
        assert snapshot.synthesis is None

    def test_create_complete_snapshot(self) -> None:
        """Test creating a snapshot with all fields."""
        snapshot_id = uuid4()
        investigation_id = uuid4()
        captured_at = datetime.now(UTC)

        snapshot = InvestigationSnapshot(
            version="1.0",
            snapshot_id=snapshot_id,
            investigation_id=investigation_id,
            checkpoint=SnapshotCheckpoint.COMPLETE,
            captured_at=captured_at,
            hypotheses=[{"id": "h1", "title": "Test hypothesis"}],
            evidence=[{"hypothesis_id": "h1", "query": "SELECT 1"}],
            lineage_snapshot=LineageSnapshot(
                target="orders",
                upstream=["customers"],
                downstream=["revenue"],
            ),
            sample_data_inline={"orders": b"parquet_data"},
            environment=EnvironmentMetadata(
                python_version="3.11.0",
                platform="linux",
            ),
            metadata={"custom_key": "custom_value"},
        )

        assert snapshot.snapshot_id == snapshot_id
        assert snapshot.investigation_id == investigation_id
        assert snapshot.checkpoint == SnapshotCheckpoint.COMPLETE
        assert len(snapshot.hypotheses) == 1
        assert len(snapshot.evidence) == 1
        assert snapshot.lineage_snapshot is not None
        assert snapshot.lineage_snapshot.target == "orders"
        assert "orders" in snapshot.sample_data_inline
        assert snapshot.metadata["custom_key"] == "custom_value"

    def test_estimated_size_bytes(self) -> None:
        """Test size estimation."""
        # Empty snapshot
        snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.START,
        )
        size = snapshot.estimated_size_bytes()
        assert size > 0

        # Snapshot with sample data
        snapshot_with_data = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.COMPLETE,
            sample_data_inline={"orders": b"x" * 10000},
        )
        size_with_data = snapshot_with_data.estimated_size_bytes()
        assert size_with_data > size
        assert size_with_data >= 10000

    def test_is_oversized(self) -> None:
        """Test oversized detection."""
        # Small snapshot
        small_snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.START,
            max_inline_size_bytes=100000,
        )
        assert not small_snapshot.is_oversized()

        # Large snapshot (set low limit)
        large_snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.COMPLETE,
            sample_data_inline={"orders": b"x" * 50000},
            max_inline_size_bytes=10000,
        )
        assert large_snapshot.is_oversized()

    def test_get_sample_table_names(self) -> None:
        """Test getting all sample table names."""
        snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.COMPLETE,
            sample_data_inline={
                "orders": b"data1",
                "customers": b"data2",
            },
            sample_data_refs=[
                SampleDataReference(
                    table_name="products",
                    storage_path="s3://bucket/products.parquet",
                    format=SampleDataFormat.PARQUET,
                    row_count=1000,
                    size_bytes=5000,
                )
            ],
        )

        table_names = snapshot.get_sample_table_names()
        assert len(table_names) == 3
        assert "orders" in table_names
        assert "customers" in table_names
        assert "products" in table_names

    def test_default_max_values(self) -> None:
        """Test default max sample rows and inline size."""
        snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.START,
        )
        assert snapshot.max_sample_rows == 10000
        assert snapshot.max_inline_size_bytes == 10 * 1024 * 1024  # 10MB

    def test_schema_versioning(self) -> None:
        """Test that version field supports schema evolution."""
        snapshot_v1 = InvestigationSnapshot(
            version="1.0",
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.START,
        )
        assert snapshot_v1.version == "1.0"

        # Future version should also work
        snapshot_v2 = InvestigationSnapshot(
            version="2.0",
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.START,
        )
        assert snapshot_v2.version == "2.0"
