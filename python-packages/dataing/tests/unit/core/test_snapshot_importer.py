"""Unit tests for snapshot archive importer."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from dataing.core.exceptions import SnapshotSizeExceededError
from dataing.core.snapshot_builder import SnapshotBuilder
from dataing.core.snapshot_importer import ImportResult, SnapshotImporter, has_parquet_support
from dataing.core.snapshot_schema import (
    SNAPSHOT_SCHEMA_VERSION,
    InvalidSnapshotError,
    UnsupportedSchemaVersionError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_archive(tmp_path: Path) -> Path:
    """Create a valid snapshot archive for testing."""
    builder = SnapshotBuilder("test-inv-123")

    async def build_archive() -> Path:
        return await builder.build(
            investigation_state={"status": "complete", "tenant_id": "test-tenant"},
            evidence_items=[
                {
                    "seq": 1,
                    "kind": "hypothesis",
                    "content_hash": "a" * 64,
                    "hypothesis_text": "Test hypothesis",
                },
                {
                    "seq": 2,
                    "kind": "query_result",
                    "content_hash": "b" * 64,
                    "sql": "SELECT 1",
                    "row_count": 1,
                    "sample_rows": [{"id": 1}],
                },
            ],
            prompts={"hypothesis": "Test prompt"},
        )

    import asyncio

    return asyncio.run(build_archive())


@pytest.fixture
def invalid_archive(tmp_path: Path) -> Path:
    """Create an invalid archive (not a tar.gz)."""
    path = tmp_path / "invalid.tar.gz"
    path.write_bytes(b"not a tar file")
    return path


@pytest.fixture
def archive_without_metadata(tmp_path: Path) -> Path:
    """Create a tar.gz without metadata.json."""
    path = tmp_path / "no-metadata.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        # Add a dummy file
        data = b"test content"
        info = tarfile.TarInfo(name="snapshot-test/dummy.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return path


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
# SnapshotImporter.__init__
# ---------------------------------------------------------------------------


class TestSnapshotImporterInit:
    """Tests for SnapshotImporter initialization."""

    def test_default_max_size(self) -> None:
        """Default max_size_bytes is 100MB."""
        importer = SnapshotImporter()
        assert importer.max_size_bytes == 100 * 1024 * 1024

    def test_custom_max_size(self) -> None:
        """Custom max_size_bytes can be set."""
        importer = SnapshotImporter(max_size_bytes=50 * 1024 * 1024)
        assert importer.max_size_bytes == 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# SnapshotImporter.validate_archive
# ---------------------------------------------------------------------------


class TestValidateArchive:
    """Tests for SnapshotImporter.validate_archive method."""

    def test_valid_archive(self, valid_archive: Path) -> None:
        """Returns SnapshotMetadata for valid archive."""
        importer = SnapshotImporter()
        metadata = importer.validate_archive(valid_archive)
        assert metadata.investigation_id == "test-inv-123"
        assert metadata.schema_version == SNAPSHOT_SCHEMA_VERSION

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Raises InvalidSnapshotError for missing file."""
        importer = SnapshotImporter()
        with pytest.raises(InvalidSnapshotError, match="not found"):
            importer.validate_archive(tmp_path / "nonexistent.tar.gz")

    def test_invalid_tar(self, invalid_archive: Path) -> None:
        """Raises InvalidSnapshotError for invalid tar."""
        importer = SnapshotImporter()
        with pytest.raises(InvalidSnapshotError, match="Invalid tar.gz"):
            importer.validate_archive(invalid_archive)

    def test_missing_metadata(self, archive_without_metadata: Path) -> None:
        """Raises InvalidSnapshotError for archive without metadata.json."""
        importer = SnapshotImporter()
        with pytest.raises(InvalidSnapshotError, match="missing metadata.json"):
            importer.validate_archive(archive_without_metadata)

    def test_size_exceeded(self, valid_archive: Path) -> None:
        """Raises SnapshotSizeExceededError for oversized archive."""
        importer = SnapshotImporter(max_size_bytes=10)  # 10 bytes
        with pytest.raises(SnapshotSizeExceededError):
            importer.validate_archive(valid_archive)

    def test_unsupported_schema_version(self, tmp_path: Path) -> None:
        """Raises UnsupportedSchemaVersionError for unknown version."""
        # Create archive with unsupported schema version
        path = tmp_path / "future.tar.gz"
        metadata = {
            "schema_version": "99.0",
            "investigation_id": "test",
            "status": "complete",
            "evidence_count": 0,
            "files": ["metadata.json"],
        }
        with tarfile.open(path, "w:gz") as tar:
            data = json.dumps(metadata).encode()
            info = tarfile.TarInfo(name="snapshot-test/metadata.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        importer = SnapshotImporter()
        with pytest.raises(UnsupportedSchemaVersionError, match="99.0"):
            importer.validate_archive(path)

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Rejects archives with path traversal."""
        path = tmp_path / "evil.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            data = b"evil content"
            info = tarfile.TarInfo(name="../../../etc/passwd")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        importer = SnapshotImporter()
        with pytest.raises(InvalidSnapshotError, match="Path traversal"):
            importer.validate_archive(path)

    def test_absolute_path_rejected(self, tmp_path: Path) -> None:
        """Rejects archives with absolute paths."""
        path = tmp_path / "evil.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            data = b"evil content"
            info = tarfile.TarInfo(name="/etc/passwd")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        importer = SnapshotImporter()
        with pytest.raises(InvalidSnapshotError, match="Absolute path"):
            importer.validate_archive(path)


# ---------------------------------------------------------------------------
# SnapshotImporter.extract_evidence
# ---------------------------------------------------------------------------


class TestExtractEvidence:
    """Tests for SnapshotImporter.extract_evidence method."""

    def test_extracts_evidence_items(self, valid_archive: Path) -> None:
        """Extracts all evidence items from archive."""
        importer = SnapshotImporter()
        evidence = importer.extract_evidence(valid_archive)
        assert len(evidence) == 2
        assert evidence[0]["seq"] == 1
        assert evidence[0]["kind"] == "hypothesis"
        assert evidence[1]["seq"] == 2
        assert evidence[1]["kind"] == "query_result"

    def test_evidence_sorted_by_seq(self, valid_archive: Path) -> None:
        """Evidence items are sorted by sequence number."""
        importer = SnapshotImporter()
        evidence = importer.extract_evidence(valid_archive)
        seqs = [e["seq"] for e in evidence]
        assert seqs == sorted(seqs)


# ---------------------------------------------------------------------------
# SnapshotImporter.extract_prompts
# ---------------------------------------------------------------------------


class TestExtractPrompts:
    """Tests for SnapshotImporter.extract_prompts method."""

    def test_extracts_prompts(self, valid_archive: Path) -> None:
        """Extracts prompt files from archive."""
        importer = SnapshotImporter()
        prompts = importer.extract_prompts(valid_archive)
        assert "hypothesis" in prompts
        assert prompts["hypothesis"] == "Test prompt"

    def test_empty_prompts(self, tmp_path: Path) -> None:
        """Returns empty dict for archive without prompts."""
        # Create archive without prompts
        builder = SnapshotBuilder("test")

        async def build() -> Path:
            return await builder.build(
                investigation_state={"status": "complete"},
                evidence_items=[],
                prompts=None,
            )

        import asyncio

        archive = asyncio.run(build())

        importer = SnapshotImporter()
        prompts = importer.extract_prompts(archive)
        assert prompts == {}


# ---------------------------------------------------------------------------
# SnapshotImporter.import_investigation
# ---------------------------------------------------------------------------


class TestImportInvestigation:
    """Tests for SnapshotImporter.import_investigation method."""

    def test_returns_import_result(self, valid_archive: Path) -> None:
        """Returns ImportResult with correct data."""
        importer = SnapshotImporter()
        result = importer.import_investigation(valid_archive, "target-tenant")

        assert isinstance(result, ImportResult)
        assert result.original_investigation_id == "test-inv-123"
        assert result.status == "replay"
        assert result.evidence_count == 2
        assert result.schema_version == SNAPSHOT_SCHEMA_VERSION

    def test_uses_provided_investigation_id(self, valid_archive: Path) -> None:
        """Uses provided investigation ID when given."""
        importer = SnapshotImporter()
        result = importer.import_investigation(
            valid_archive,
            "target-tenant",
            new_investigation_id="custom-id-123",
        )
        assert result.investigation_id == "custom-id-123"

    def test_generates_investigation_id(self, valid_archive: Path) -> None:
        """Generates investigation ID when not provided."""
        importer = SnapshotImporter()
        result = importer.import_investigation(valid_archive, "target-tenant")
        assert result.investigation_id is not None
        assert len(result.investigation_id) > 0


# ---------------------------------------------------------------------------
# ImportResult
# ---------------------------------------------------------------------------


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_defaults(self) -> None:
        """Default values are set correctly."""
        result = ImportResult(
            investigation_id="new-id",
            original_investigation_id="orig-id",
        )
        assert result.status == "replay"
        assert result.evidence_count == 0
        assert result.source_instance is None
        assert result.schema_version == "1.0"
