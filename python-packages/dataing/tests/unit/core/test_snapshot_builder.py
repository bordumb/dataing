"""Unit tests for snapshot archive builder."""

from __future__ import annotations

import json
import tarfile
from unittest.mock import patch

import pytest

from dataing.core.exceptions import SnapshotSizeExceededError
from dataing.core.snapshot_builder import SnapshotBuilder, has_parquet_support
from dataing.core.snapshot_schema import SNAPSHOT_SCHEMA_VERSION, ArchivePaths

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def investigation_state() -> dict:
    """Sample investigation state."""
    return {
        "status": "complete",
        "source_instance": "https://dataing.example.com",
        "tenant_id": "tenant-123",
    }


@pytest.fixture
def evidence_items() -> list[dict]:
    """Sample evidence items."""
    return [
        {
            "seq": 1,
            "kind": "hypothesis",
            "content_hash": "a" * 64,
            "prev_hash": None,
            "hypothesis_text": "Null spike caused by schema change",
            "confidence": 0.8,
        },
        {
            "seq": 2,
            "kind": "query_result",
            "content_hash": "b" * 64,
            "prev_hash": "a" * 64,
            "sql": "SELECT * FROM orders LIMIT 10",
            "row_count": 5,
            "sample_rows": [
                {"id": 1, "value": "foo"},
                {"id": 2, "value": "bar"},
            ],
        },
        {
            "seq": 3,
            "kind": "run_summary",
            "content_hash": "c" * 64,
            "prev_hash": "b" * 64,
            "root_cause": "Schema migration issue",
            "confidence": 0.9,
        },
    ]


# ---------------------------------------------------------------------------
# has_parquet_support
# ---------------------------------------------------------------------------


class TestHasParquetSupport:
    """Tests for has_parquet_support function."""

    def test_returns_bool(self) -> None:
        """Returns a boolean."""
        result = has_parquet_support()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# SnapshotBuilder.__init__
# ---------------------------------------------------------------------------


class TestSnapshotBuilderInit:
    """Tests for SnapshotBuilder initialization."""

    def test_default_max_size(self) -> None:
        """Default max_size_bytes is 100MB."""
        builder = SnapshotBuilder("inv-123")
        assert builder.max_size_bytes == 100 * 1024 * 1024

    def test_custom_max_size(self) -> None:
        """Custom max_size_bytes can be set."""
        builder = SnapshotBuilder("inv-456", max_size_bytes=50 * 1024 * 1024)
        assert builder.max_size_bytes == 50 * 1024 * 1024

    def test_stores_investigation_id(self) -> None:
        """Stores the investigation ID."""
        builder = SnapshotBuilder("inv-789")
        assert builder.investigation_id == "inv-789"


# ---------------------------------------------------------------------------
# SnapshotBuilder.build
# ---------------------------------------------------------------------------


class TestSnapshotBuilderBuild:
    """Tests for SnapshotBuilder.build method."""

    async def test_produces_tar_gz(
        self, investigation_state: dict, evidence_items: list[dict]
    ) -> None:
        """Produces a .tar.gz file."""
        builder = SnapshotBuilder("inv-123")
        archive_path = await builder.build(
            investigation_state=investigation_state,
            evidence_items=evidence_items,
        )
        try:
            assert archive_path.exists()
            assert archive_path.suffix == ".gz"
            assert archive_path.stem.endswith(".tar")
        finally:
            archive_path.unlink(missing_ok=True)

    async def test_archive_has_correct_structure(
        self, investigation_state: dict, evidence_items: list[dict]
    ) -> None:
        """Archive follows the directory layout from schema."""
        builder = SnapshotBuilder("inv-123")
        archive_path = await builder.build(
            investigation_state=investigation_state,
            evidence_items=evidence_items,
        )
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                names = tar.getnames()
                # Check for expected files
                assert any(ArchivePaths.METADATA in n for n in names)
                assert any(ArchivePaths.LINEAGE in n for n in names)
                assert any(ArchivePaths.CODE_CHANGES in n for n in names)
                # Evidence files
                assert any("001-hypothesis.json" in n for n in names)
                assert any("002-query_result.json" in n for n in names)
                assert any("003-run_summary.json" in n for n in names)
        finally:
            archive_path.unlink(missing_ok=True)

    async def test_metadata_json_valid(
        self, investigation_state: dict, evidence_items: list[dict]
    ) -> None:
        """metadata.json is valid and contains expected fields."""
        builder = SnapshotBuilder("inv-123")
        archive_path = await builder.build(
            investigation_state=investigation_state,
            evidence_items=evidence_items,
        )
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                # Find metadata.json
                metadata_member = None
                for member in tar.getmembers():
                    if member.name.endswith(ArchivePaths.METADATA):
                        metadata_member = member
                        break
                assert metadata_member is not None

                # Read and parse
                f = tar.extractfile(metadata_member)
                assert f is not None
                metadata = json.load(f)

                # Verify fields
                assert metadata["schema_version"] == SNAPSHOT_SCHEMA_VERSION
                assert metadata["investigation_id"] == "inv-123"
                assert metadata["status"] == "complete"
                assert metadata["evidence_count"] == 3
                assert metadata["root_hash"] == "c" * 64  # Last item's hash
                assert "files" in metadata
                assert len(metadata["files"]) > 0
        finally:
            archive_path.unlink(missing_ok=True)

    async def test_evidence_serialized_as_json(
        self, investigation_state: dict, evidence_items: list[dict]
    ) -> None:
        """Evidence items are serialized as JSON."""
        builder = SnapshotBuilder("inv-123")
        archive_path = await builder.build(
            investigation_state=investigation_state,
            evidence_items=evidence_items,
        )
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                # Find first evidence file
                evidence_member = None
                for member in tar.getmembers():
                    if "001-hypothesis.json" in member.name:
                        evidence_member = member
                        break
                assert evidence_member is not None

                # Read and verify
                f = tar.extractfile(evidence_member)
                assert f is not None
                evidence = json.load(f)
                assert evidence["kind"] == "hypothesis"
                assert evidence["seq"] == 1
        finally:
            archive_path.unlink(missing_ok=True)

    async def test_prompts_written(
        self, investigation_state: dict, evidence_items: list[dict]
    ) -> None:
        """Prompts are written to prompts/ directory."""
        builder = SnapshotBuilder("inv-123")
        prompts = {
            "hypothesis": "Generate hypotheses for this anomaly...",
            "query": "Generate SQL to test hypothesis...",
            "synthesis": "Synthesize findings...",
        }
        archive_path = await builder.build(
            investigation_state=investigation_state,
            evidence_items=evidence_items,
            prompts=prompts,
        )
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                names = tar.getnames()
                assert any("prompts/hypothesis.txt" in n for n in names)
                assert any("prompts/query.txt" in n for n in names)
                assert any("prompts/synthesis.txt" in n for n in names)
        finally:
            archive_path.unlink(missing_ok=True)

    async def test_lineage_written(
        self, investigation_state: dict, evidence_items: list[dict]
    ) -> None:
        """Lineage is written to lineage.json."""
        builder = SnapshotBuilder("inv-123")
        lineage = {
            "target": "orders",
            "upstream": ["customers", "products"],
            "downstream": ["order_reports"],
        }
        archive_path = await builder.build(
            investigation_state=investigation_state,
            evidence_items=evidence_items,
            lineage=lineage,
        )
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                lineage_member = None
                for member in tar.getmembers():
                    if member.name.endswith(ArchivePaths.LINEAGE):
                        lineage_member = member
                        break
                assert lineage_member is not None
                f = tar.extractfile(lineage_member)
                assert f is not None
                data = json.load(f)
                assert data["target"] == "orders"
        finally:
            archive_path.unlink(missing_ok=True)

    async def test_empty_lineage_and_code_changes(
        self, investigation_state: dict, evidence_items: list[dict]
    ) -> None:
        """Empty lineage and code_changes are written as empty objects."""
        builder = SnapshotBuilder("inv-123")
        archive_path = await builder.build(
            investigation_state=investigation_state,
            evidence_items=evidence_items,
        )
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                # Check lineage.json
                lineage_member = None
                for member in tar.getmembers():
                    if member.name.endswith(ArchivePaths.LINEAGE):
                        lineage_member = member
                        break
                assert lineage_member is not None
                f = tar.extractfile(lineage_member)
                assert f is not None
                assert json.load(f) == {}

                # Check code_changes.json
                code_member = None
                for member in tar.getmembers():
                    if member.name.endswith(ArchivePaths.CODE_CHANGES):
                        code_member = member
                        break
                assert code_member is not None
                f = tar.extractfile(code_member)
                assert f is not None
                assert json.load(f) == {}
        finally:
            archive_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Size limit enforcement
# ---------------------------------------------------------------------------


class TestSnapshotSizeLimit:
    """Tests for snapshot size limit enforcement."""

    async def test_raises_on_size_exceeded(self) -> None:
        """Raises SnapshotSizeExceededError when archive exceeds max_size."""
        # Use a tiny max_size to trigger the error
        builder = SnapshotBuilder("inv-123", max_size_bytes=10)

        with pytest.raises(SnapshotSizeExceededError) as exc_info:
            await builder.build(
                investigation_state={"status": "complete"},
                evidence_items=[{"seq": 1, "kind": "test", "data": "x" * 100}],
            )

        assert exc_info.value.max_size == 10
        assert exc_info.value.actual_size > 10

    async def test_does_not_raise_under_limit(self) -> None:
        """Does not raise when archive is under max_size."""
        builder = SnapshotBuilder("inv-123", max_size_bytes=100 * 1024 * 1024)

        archive_path = await builder.build(
            investigation_state={"status": "complete"},
            evidence_items=[{"seq": 1, "kind": "test"}],
        )
        try:
            assert archive_path.exists()
        finally:
            archive_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Parquet support
# ---------------------------------------------------------------------------


class TestParquetSupport:
    """Tests for Parquet serialization."""

    @pytest.mark.skipif(not has_parquet_support(), reason="pyarrow not installed")
    async def test_query_results_as_parquet(self) -> None:
        """Query results with sample_rows are written as Parquet when available."""
        builder = SnapshotBuilder("inv-123")
        evidence = [
            {
                "seq": 1,
                "kind": "query_result",
                "content_hash": "a" * 64,
                "sql": "SELECT 1",
                "row_count": 2,
                "sample_rows": [
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                ],
            }
        ]
        archive_path = await builder.build(
            investigation_state={"status": "complete"},
            evidence_items=evidence,
        )
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                names = tar.getnames()
                # Should have Parquet file
                assert any("001-results.parquet" in n for n in names)
        finally:
            archive_path.unlink(missing_ok=True)

    async def test_falls_back_to_json_without_pyarrow(self) -> None:
        """Falls back to JSON when pyarrow is not available."""
        builder = SnapshotBuilder("inv-123")
        evidence = [
            {
                "seq": 1,
                "kind": "query_result",
                "content_hash": "a" * 64,
                "sql": "SELECT 1",
                "row_count": 2,
                "sample_rows": [
                    {"id": 1, "name": "Alice"},
                ],
            }
        ]

        # Mock pyarrow as unavailable
        with patch("dataing.core.snapshot_builder._HAS_PYARROW", False):
            archive_path = await builder.build(
                investigation_state={"status": "complete"},
                evidence_items=evidence,
            )
            try:
                with tarfile.open(archive_path, "r:gz") as tar:
                    names = tar.getnames()
                    # Should have JSON fallback instead of Parquet
                    assert any("001-results.json" in n for n in names)
                    assert not any("001-results.parquet" in n for n in names)
            finally:
                archive_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    async def test_empty_evidence(self) -> None:
        """Handles empty evidence list."""
        builder = SnapshotBuilder("inv-123")
        archive_path = await builder.build(
            investigation_state={"status": "complete"},
            evidence_items=[],
        )
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                # Find metadata
                metadata_member = None
                for member in tar.getmembers():
                    if member.name.endswith(ArchivePaths.METADATA):
                        metadata_member = member
                        break
                assert metadata_member is not None
                f = tar.extractfile(metadata_member)
                assert f is not None
                metadata = json.load(f)
                assert metadata["evidence_count"] == 0
                assert metadata["root_hash"] is None
        finally:
            archive_path.unlink(missing_ok=True)

    async def test_evidence_without_content_hash(self) -> None:
        """Handles evidence items without content_hash."""
        builder = SnapshotBuilder("inv-123")
        evidence = [{"seq": 1, "kind": "test"}]  # No content_hash
        archive_path = await builder.build(
            investigation_state={"status": "complete"},
            evidence_items=evidence,
        )
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                metadata_member = None
                for member in tar.getmembers():
                    if member.name.endswith(ArchivePaths.METADATA):
                        metadata_member = member
                        break
                assert metadata_member is not None
                f = tar.extractfile(metadata_member)
                assert f is not None
                metadata = json.load(f)
                assert metadata["root_hash"] is None
        finally:
            archive_path.unlink(missing_ok=True)

    async def test_archive_directory_name(self) -> None:
        """Archive has correct top-level directory name."""
        builder = SnapshotBuilder("inv-abc-123")
        archive_path = await builder.build(
            investigation_state={"status": "complete"},
            evidence_items=[],
        )
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                names = tar.getnames()
                assert all(n.startswith("snapshot-inv-abc-123/") for n in names)
        finally:
            archive_path.unlink(missing_ok=True)
