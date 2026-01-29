"""Unit tests for capture_snapshot activity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from dataing.core.snapshot import InvestigationSnapshot, SnapshotCheckpoint
from dataing.temporal.activities.capture_snapshot import (
    CaptureSnapshotInput,
)

if TYPE_CHECKING:
    pass


class MockSnapshotStore:
    """Mock snapshot store for testing."""

    def __init__(self, should_fail: bool = False) -> None:
        """Initialize mock store."""
        self.stored_snapshots: list[tuple[InvestigationSnapshot, str]] = []
        self.should_fail = should_fail
        self.fail_message = "Mock storage error"

    async def store(
        self,
        snapshot: InvestigationSnapshot,
        tenant_id: str,
    ) -> str:
        """Mock store that tracks calls."""
        if self.should_fail:
            raise Exception(self.fail_message)

        self.stored_snapshots.append((snapshot, tenant_id))
        path = (
            f"/mock/path/{tenant_id}/{snapshot.investigation_id}/"
            f"{snapshot.checkpoint.value}.snapshot"
        )
        return path


async def _execute_capture(
    mock_store: MockSnapshotStore,
    input_data: CaptureSnapshotInput,
) -> tuple[bool, str | None, str | None]:
    """Execute capture logic without Temporal context.

    Returns:
        Tuple of (success, storage_path, error).
    """
    from uuid import UUID

    from dataing.core.snapshot import (
        EnvironmentMetadata,
        InvestigationSnapshot,
        LineageSnapshot,
        SnapshotCheckpoint,
    )

    try:
        # Parse checkpoint
        try:
            checkpoint = SnapshotCheckpoint(input_data.checkpoint)
        except ValueError:
            return (False, None, f"Invalid checkpoint: {input_data.checkpoint}")

        # Build lineage snapshot if provided
        lineage_snapshot = None
        if input_data.lineage_snapshot:
            lineage_snapshot = LineageSnapshot(
                target=input_data.lineage_snapshot.get("target", ""),
                upstream=input_data.lineage_snapshot.get("upstream", []),
                downstream=input_data.lineage_snapshot.get("downstream", []),
                depth=input_data.lineage_snapshot.get("depth", 2),
            )

        # Create snapshot
        snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=UUID(input_data.investigation_id),
            checkpoint=checkpoint,
            alert=input_data.alert,
            hypotheses=input_data.hypotheses or [],
            evidence=input_data.evidence or [],
            synthesis=input_data.synthesis,
            schema_snapshot=input_data.schema_snapshot,
            lineage_snapshot=lineage_snapshot,
            sample_data_inline=input_data.sample_data_inline or {},
            environment=EnvironmentMetadata.capture_current(),
            metadata=input_data.metadata or {},
        )

        # Store snapshot
        storage_path = await mock_store.store(snapshot, input_data.tenant_id)
        return (True, storage_path, None)

    except Exception as e:
        return (False, None, str(e))


class TestCaptureSnapshotActivity:
    """Tests for capture_snapshot activity logic."""

    @pytest.fixture
    def mock_store(self) -> MockSnapshotStore:
        """Create mock snapshot store."""
        return MockSnapshotStore()

    async def test_capture_start_checkpoint(
        self,
        mock_store: MockSnapshotStore,
    ) -> None:
        """Test capturing snapshot at start checkpoint."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant-123",
            checkpoint="start",
            alert={"dataset_id": "orders", "anomaly_type": "volume_drop"},
        )

        success, storage_path, error = await _execute_capture(mock_store, input_data)

        assert success
        assert storage_path is not None
        assert "start.snapshot" in storage_path
        assert len(mock_store.stored_snapshots) == 1

        snapshot, tenant_id = mock_store.stored_snapshots[0]
        assert tenant_id == "tenant-123"
        assert snapshot.checkpoint == SnapshotCheckpoint.START

    async def test_capture_complete_checkpoint(
        self,
        mock_store: MockSnapshotStore,
    ) -> None:
        """Test capturing snapshot at complete checkpoint."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant-456",
            checkpoint="complete",
            alert={"dataset_id": "orders"},
            hypotheses=[{"id": "h1", "title": "Data pipeline delay"}],
            evidence=[{"hypothesis_id": "h1", "supports": True}],
            synthesis={"root_cause": "Upstream ETL job failure"},
        )

        success, storage_path, _ = await _execute_capture(mock_store, input_data)

        assert success
        assert "complete.snapshot" in storage_path

        snapshot, _ = mock_store.stored_snapshots[0]
        assert snapshot.checkpoint == SnapshotCheckpoint.COMPLETE
        assert len(snapshot.hypotheses) == 1
        assert len(snapshot.evidence) == 1

    async def test_capture_hypothesis_generated_checkpoint(
        self,
        mock_store: MockSnapshotStore,
    ) -> None:
        """Test capturing snapshot at hypothesis_generated checkpoint."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="hypothesis_generated",
            hypotheses=[
                {"id": "h1", "title": "Hypothesis 1"},
                {"id": "h2", "title": "Hypothesis 2"},
            ],
        )

        success, _, _ = await _execute_capture(mock_store, input_data)

        assert success
        snapshot, _ = mock_store.stored_snapshots[0]
        assert snapshot.checkpoint == SnapshotCheckpoint.HYPOTHESIS_GENERATED
        assert len(snapshot.hypotheses) == 2

    async def test_capture_failed_checkpoint(
        self,
        mock_store: MockSnapshotStore,
    ) -> None:
        """Test capturing snapshot at failed checkpoint."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="failed",
            metadata={"error": "Connection timeout"},
        )

        success, _, _ = await _execute_capture(mock_store, input_data)

        assert success
        snapshot, _ = mock_store.stored_snapshots[0]
        assert snapshot.checkpoint == SnapshotCheckpoint.FAILED

    async def test_capture_evidence_collected_checkpoint(
        self,
        mock_store: MockSnapshotStore,
    ) -> None:
        """Test capturing snapshot at evidence_collected checkpoint."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="evidence_collected",
            evidence=[{"hypothesis_id": "h1", "query": "SELECT COUNT(*) FROM orders"}],
        )

        success, _, _ = await _execute_capture(mock_store, input_data)

        assert success
        snapshot, _ = mock_store.stored_snapshots[0]
        assert snapshot.checkpoint == SnapshotCheckpoint.EVIDENCE_COLLECTED

    async def test_capture_with_lineage_snapshot(
        self,
        mock_store: MockSnapshotStore,
    ) -> None:
        """Test capturing snapshot with lineage context."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="start",
            lineage_snapshot={
                "target": "analytics.orders",
                "upstream": ["raw.orders", "raw.customers"],
                "downstream": ["analytics.revenue"],
                "depth": 2,
            },
        )

        success, _, _ = await _execute_capture(mock_store, input_data)

        assert success
        snapshot, _ = mock_store.stored_snapshots[0]
        assert snapshot.lineage_snapshot is not None
        assert snapshot.lineage_snapshot.target == "analytics.orders"
        assert len(snapshot.lineage_snapshot.upstream) == 2

    async def test_capture_with_schema_snapshot(
        self,
        mock_store: MockSnapshotStore,
    ) -> None:
        """Test capturing snapshot with schema context."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="start",
            schema_snapshot={
                "target_table": {
                    "name": "orders",
                    "columns": [{"name": "id", "type": "integer"}],
                }
            },
        )

        success, _, _ = await _execute_capture(mock_store, input_data)

        assert success
        snapshot, _ = mock_store.stored_snapshots[0]
        assert snapshot.schema_snapshot is not None

    async def test_invalid_checkpoint_returns_error(
        self,
        mock_store: MockSnapshotStore,
    ) -> None:
        """Test that invalid checkpoint returns error result."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="invalid_checkpoint",
        )

        success, _, error = await _execute_capture(mock_store, input_data)

        assert not success
        assert error is not None
        assert "Invalid checkpoint" in error
        assert len(mock_store.stored_snapshots) == 0

    async def test_store_failure_returns_error(self) -> None:
        """Test that store failure returns error result (non-blocking)."""
        failing_store = MockSnapshotStore(should_fail=True)

        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="start",
        )

        success, _, error = await _execute_capture(failing_store, input_data)

        assert not success
        assert error is not None
        assert "Mock storage error" in error

    async def test_captures_environment_metadata(
        self,
        mock_store: MockSnapshotStore,
    ) -> None:
        """Test that environment metadata is captured."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="start",
        )

        success, _, _ = await _execute_capture(mock_store, input_data)

        assert success
        snapshot, _ = mock_store.stored_snapshots[0]
        assert snapshot.environment is not None
        assert snapshot.environment.python_version is not None
        assert snapshot.environment.platform is not None

    async def test_generates_unique_snapshot_id(
        self,
        mock_store: MockSnapshotStore,
    ) -> None:
        """Test that each snapshot gets a unique ID."""
        investigation_id = str(uuid4())

        # Capture two snapshots
        for checkpoint in ["start", "complete"]:
            input_data = CaptureSnapshotInput(
                investigation_id=investigation_id,
                tenant_id="tenant",
                checkpoint=checkpoint,
            )
            await _execute_capture(mock_store, input_data)

        assert len(mock_store.stored_snapshots) == 2
        snapshot1, _ = mock_store.stored_snapshots[0]
        snapshot2, _ = mock_store.stored_snapshots[1]
        assert snapshot1.snapshot_id != snapshot2.snapshot_id


class TestCaptureSnapshotInput:
    """Tests for CaptureSnapshotInput dataclass."""

    def test_required_fields(self) -> None:
        """Test that required fields are properly validated."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="start",
        )
        assert input_data.investigation_id is not None
        assert input_data.tenant_id == "tenant"
        assert input_data.checkpoint == "start"

    def test_optional_fields_default_none(self) -> None:
        """Test that optional fields default to None."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="start",
        )
        assert input_data.alert is None
        assert input_data.hypotheses is None
        assert input_data.evidence is None
        assert input_data.synthesis is None
        assert input_data.schema_snapshot is None
        assert input_data.lineage_snapshot is None
        assert input_data.metadata is None

    def test_all_fields_populated(self) -> None:
        """Test creating input with all fields."""
        input_data = CaptureSnapshotInput(
            investigation_id=str(uuid4()),
            tenant_id="tenant",
            checkpoint="complete",
            alert={"dataset_id": "orders"},
            hypotheses=[{"id": "h1"}],
            evidence=[{"id": "e1"}],
            synthesis={"root_cause": "test"},
            schema_snapshot={"tables": []},
            lineage_snapshot={"target": "orders"},
            sample_data_inline={"orders": b"data"},
            metadata={"key": "value"},
        )
        assert input_data.alert is not None
        assert input_data.hypotheses is not None
        assert input_data.sample_data_inline is not None
