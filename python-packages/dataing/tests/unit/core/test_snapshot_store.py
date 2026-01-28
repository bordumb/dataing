"""Unit tests for snapshot storage implementations."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from dataing.core.snapshot import (
    InvestigationSnapshot,
    SnapshotCheckpoint,
)
from dataing.core.snapshot_store import (
    LocalSnapshotStore,
    SnapshotNotFoundError,
)


class TestLocalSnapshotStore:
    """Tests for LocalSnapshotStore implementation."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that initialization creates the base directory."""
        new_path = tmp_path / "snapshots" / "nested"
        store = LocalSnapshotStore(new_path)
        assert store.base_path.exists()

    def test_build_path(self, tmp_path: Path) -> None:
        """Test storage path generation."""
        store = LocalSnapshotStore(tmp_path)
        snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.START,
        )
        tenant_id = "tenant-123"

        path = store._build_path(tenant_id, snapshot)

        assert tenant_id in str(path)
        assert "snapshots" in str(path)
        assert str(snapshot.investigation_id) in str(path)
        assert "start.snapshot" in str(path)

    async def test_store_and_retrieve(self, tmp_path: Path) -> None:
        """Test storing and retrieving a snapshot."""
        store = LocalSnapshotStore(tmp_path)
        tenant_id = "tenant-456"
        original = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.COMPLETE,
            hypotheses=[{"id": "h1", "title": "Test hypothesis"}],
            evidence=[{"hypothesis_id": "h1", "query": "SELECT 1"}],
            metadata={"test_key": "test_value"},
        )

        # Store
        storage_path = await store.store(original, tenant_id)
        assert Path(storage_path).exists()

        # Retrieve
        retrieved = await store.retrieve(storage_path)
        assert retrieved.snapshot_id == original.snapshot_id
        assert retrieved.investigation_id == original.investigation_id
        assert retrieved.checkpoint == original.checkpoint
        assert len(retrieved.hypotheses) == 1
        assert len(retrieved.evidence) == 1
        assert retrieved.metadata["test_key"] == "test_value"

    async def test_exists_true(self, tmp_path: Path) -> None:
        """Test exists returns True for stored snapshot."""
        store = LocalSnapshotStore(tmp_path)
        snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.START,
        )

        storage_path = await store.store(snapshot, "tenant")
        assert await store.exists(storage_path)

    async def test_exists_false(self, tmp_path: Path) -> None:
        """Test exists returns False for non-existent path."""
        store = LocalSnapshotStore(tmp_path)
        assert not await store.exists("/nonexistent/path.snapshot")

    async def test_retrieve_not_found(self, tmp_path: Path) -> None:
        """Test retrieve raises SnapshotNotFoundError for missing snapshot."""
        store = LocalSnapshotStore(tmp_path)

        with pytest.raises(SnapshotNotFoundError):
            await store.retrieve("/nonexistent/path.snapshot")

    async def test_store_all_checkpoints(self, tmp_path: Path) -> None:
        """Test storing snapshots at all checkpoints."""
        store = LocalSnapshotStore(tmp_path)
        tenant_id = "tenant"
        investigation_id = uuid4()

        for checkpoint in SnapshotCheckpoint:
            snapshot = InvestigationSnapshot(
                snapshot_id=uuid4(),
                investigation_id=investigation_id,
                checkpoint=checkpoint,
            )
            storage_path = await store.store(snapshot, tenant_id)
            assert Path(storage_path).exists()
            assert f"{checkpoint.value}.snapshot" in storage_path

    async def test_store_with_sample_data(self, tmp_path: Path) -> None:
        """Test storing snapshot with inline sample data."""
        store = LocalSnapshotStore(tmp_path)
        sample_data = b"test binary data for sample"
        snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.COMPLETE,
            sample_data_inline={"orders": sample_data},
        )

        storage_path = await store.store(snapshot, "tenant")
        retrieved = await store.retrieve(storage_path)

        # Note: bytes are base64 encoded in JSON, Pydantic handles conversion
        assert "orders" in retrieved.sample_data_inline

    async def test_store_overwrites_same_checkpoint(self, tmp_path: Path) -> None:
        """Test that storing at same checkpoint overwrites previous snapshot."""
        store = LocalSnapshotStore(tmp_path)
        tenant_id = "tenant"
        investigation_id = uuid4()

        # Store first snapshot
        snapshot1 = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=investigation_id,
            checkpoint=SnapshotCheckpoint.START,
            metadata={"version": 1},
        )
        path1 = await store.store(snapshot1, tenant_id)

        # Store second snapshot at same checkpoint
        snapshot2 = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=investigation_id,
            checkpoint=SnapshotCheckpoint.START,
            metadata={"version": 2},
        )
        path2 = await store.store(snapshot2, tenant_id)

        # Same path
        assert path1 == path2

        # Second version persisted
        retrieved = await store.retrieve(path1)
        assert retrieved.metadata["version"] == 2


class TestS3SnapshotStore:
    """Tests for S3SnapshotStore implementation.

    These tests verify the S3 store's key building logic without
    requiring actual AWS credentials or network access.
    """

    def test_build_key_without_prefix(self) -> None:
        """Test S3 key generation without prefix."""
        from dataing.core.snapshot_store import S3SnapshotStore

        store = S3SnapshotStore(bucket="test-bucket")
        snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.COMPLETE,
        )

        key = store._build_key("tenant-123", snapshot)

        assert key.startswith("tenant-123/snapshots/")
        assert key.endswith("/complete.snapshot")
        assert str(snapshot.investigation_id) in key

    def test_build_key_with_prefix(self) -> None:
        """Test S3 key generation with prefix."""
        from dataing.core.snapshot_store import S3SnapshotStore

        store = S3SnapshotStore(bucket="test-bucket", prefix="prod/data")
        snapshot = InvestigationSnapshot(
            snapshot_id=uuid4(),
            investigation_id=uuid4(),
            checkpoint=SnapshotCheckpoint.START,
        )

        key = store._build_key("tenant-456", snapshot)

        assert key.startswith("prod/data/tenant-456/snapshots/")
        assert key.endswith("/start.snapshot")

    def test_build_key_strips_prefix_slashes(self) -> None:
        """Test that prefix slashes are stripped."""
        from dataing.core.snapshot_store import S3SnapshotStore

        store = S3SnapshotStore(bucket="test-bucket", prefix="/leading/trailing/")
        assert store.prefix == "leading/trailing"
