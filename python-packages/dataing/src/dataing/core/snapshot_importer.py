"""Snapshot archive importer for investigation replay.

This module provides the SnapshotImporter class that reads compressed tar.gz
archives and reconstitutes investigations as replay records.
"""

from __future__ import annotations

import json
import logging
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dataing.core.exceptions import SnapshotSizeExceededError
from dataing.core.snapshot_schema import (
    SUPPORTED_SCHEMA_VERSIONS,
    ArchivePaths,
    InvalidSnapshotError,
    SnapshotMetadata,
    UnsupportedSchemaVersionError,
    validate_metadata,
)

logger = logging.getLogger(__name__)

# Check for optional pyarrow dependency
_HAS_PYARROW = False
try:
    import pyarrow.parquet as pq

    _HAS_PYARROW = True
except ImportError:
    pq = None


def has_parquet_support() -> bool:
    """Check if Parquet reading is available.

    Returns:
        True if pyarrow is installed, False otherwise.
    """
    return _HAS_PYARROW


@dataclass
class ImportResult:
    """Result of importing a snapshot archive.

    Attributes:
        investigation_id: ID of the newly created replay investigation.
        original_investigation_id: ID of the original investigation.
        status: Import status ("imported").
        evidence_count: Number of evidence items imported.
        source_instance: URL of the originating server (if available).
        imported_at: Timestamp of the import.
        original_created_at: Original investigation creation timestamp.
        schema_version: Schema version of the imported snapshot.
    """

    investigation_id: str
    original_investigation_id: str
    status: str = "replay"
    evidence_count: int = 0
    source_instance: str | None = None
    imported_at: datetime | None = None
    original_created_at: datetime | None = None
    schema_version: str = "1.0"


class SnapshotImporter:
    """Import a snapshot archive and create a replayed investigation.

    Reads tar.gz archives created by SnapshotBuilder and reconstitutes
    investigations as replay records. Validates schema version for
    forward compatibility.

    Attributes:
        max_size_bytes: Maximum allowed archive size (default 100MB).
    """

    def __init__(self, max_size_bytes: int = 100 * 1024 * 1024) -> None:
        """Initialize the SnapshotImporter.

        Args:
            max_size_bytes: Maximum allowed archive size in bytes.
        """
        self.max_size_bytes = max_size_bytes

    def validate_archive(self, archive_path: Path) -> SnapshotMetadata:
        """Extract and validate metadata.json from archive.

        Args:
            archive_path: Path to the .tar.gz archive file.

        Returns:
            Validated SnapshotMetadata instance.

        Raises:
            InvalidSnapshotError: If archive is malformed or missing metadata.
            UnsupportedSchemaVersionError: If schema version is not supported.
            SnapshotSizeExceededError: If archive exceeds max_size_bytes.
        """
        # Check file size
        if not archive_path.exists():
            raise InvalidSnapshotError(f"Archive file not found: {archive_path}")

        file_size = archive_path.stat().st_size
        if file_size > self.max_size_bytes:
            raise SnapshotSizeExceededError(file_size, self.max_size_bytes)

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                # Security check: validate all paths
                self._validate_tar_paths(tar)

                # Find and read metadata.json
                metadata = self._read_metadata(tar)

                # Validate schema version
                if metadata.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
                    raise UnsupportedSchemaVersionError(metadata.schema_version)

                # Validate file inventory
                self._validate_file_inventory(tar, metadata)

                return metadata

        except tarfile.TarError as e:
            raise InvalidSnapshotError(f"Invalid tar.gz archive: {e}") from e

    def extract_evidence(self, archive_path: Path) -> list[dict[str, Any]]:
        """Extract all evidence items from the archive.

        Args:
            archive_path: Path to the .tar.gz archive file.

        Returns:
            List of evidence item dicts ordered by sequence number.
        """
        evidence_items: list[dict[str, Any]] = []

        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                # Match evidence JSON files
                if ArchivePaths.EVIDENCE_DIR in member.name and member.name.endswith(".json"):
                    # Skip -results.json files (those are from Parquet fallback)
                    if "-results.json" in member.name:
                        continue

                    f = tar.extractfile(member)
                    if f is not None:
                        try:
                            item = json.load(f)
                            evidence_items.append(item)
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse evidence file: {member.name}")

        # Sort by sequence number
        evidence_items.sort(key=lambda x: x.get("seq", 0))

        # Try to read Parquet files for query results
        if _HAS_PYARROW:
            evidence_items = self._merge_parquet_results(archive_path, evidence_items)

        return evidence_items

    def extract_prompts(self, archive_path: Path) -> dict[str, str]:
        """Extract prompt templates from the archive.

        Args:
            archive_path: Path to the .tar.gz archive file.

        Returns:
            Dict mapping prompt names to prompt text.
        """
        prompts: dict[str, str] = {}
        prompt_files = {
            ArchivePaths.PROMPT_HYPOTHESIS: "hypothesis",
            ArchivePaths.PROMPT_QUERY: "query",
            ArchivePaths.PROMPT_SYNTHESIS: "synthesis",
        }

        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                for filename, name in prompt_files.items():
                    if member.name.endswith(filename):
                        f = tar.extractfile(member)
                        if f is not None:
                            prompts[name] = f.read().decode("utf-8")
                        break

        return prompts

    def extract_lineage(self, archive_path: Path) -> dict[str, Any] | None:
        """Extract lineage data from the archive.

        Args:
            archive_path: Path to the .tar.gz archive file.

        Returns:
            Lineage dict or None if not present.
        """
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(ArchivePaths.LINEAGE):
                    f = tar.extractfile(member)
                    if f is not None:
                        try:
                            data = json.load(f)
                            return data if data else None
                        except json.JSONDecodeError:
                            return None
        return None

    def import_investigation(
        self,
        archive_path: Path,
        target_tenant_id: str,
        new_investigation_id: str | None = None,
    ) -> ImportResult:
        """Full import: validate, extract, and return import result.

        This method validates the archive, extracts all data, and returns
        an ImportResult with all the information needed to create the
        investigation record in the database.

        Args:
            archive_path: Path to the .tar.gz archive file.
            target_tenant_id: Tenant ID for the imported investigation.
            new_investigation_id: Optional ID for the new investigation.

        Returns:
            ImportResult with all imported data.

        Raises:
            InvalidSnapshotError: If archive is malformed.
            UnsupportedSchemaVersionError: If schema version is not supported.
            SnapshotSizeExceededError: If archive exceeds max_size_bytes.
        """
        from uuid import uuid4

        # Validate archive
        metadata = self.validate_archive(archive_path)

        # Extract evidence
        evidence_items = self.extract_evidence(archive_path)

        # Generate new investigation ID if not provided
        inv_id = new_investigation_id or str(uuid4())

        return ImportResult(
            investigation_id=inv_id,
            original_investigation_id=metadata.investigation_id,
            status="replay",
            evidence_count=len(evidence_items),
            source_instance=metadata.source_instance,
            imported_at=datetime.now(UTC),
            original_created_at=metadata.created_at,
            schema_version=metadata.schema_version,
        )

    def _validate_tar_paths(self, tar: tarfile.TarFile) -> None:
        """Validate all tar entries for path traversal attacks.

        Args:
            tar: Open tarfile to validate.

        Raises:
            InvalidSnapshotError: If any entry has unsafe path.
        """
        for member in tar.getmembers():
            # Check for absolute paths
            if member.name.startswith("/"):
                raise InvalidSnapshotError(f"Absolute path in archive: {member.name}")

            # Check for path traversal
            if ".." in member.name:
                raise InvalidSnapshotError(f"Path traversal in archive: {member.name}")

            # Check for symlinks (security risk)
            if member.issym() or member.islnk():
                raise InvalidSnapshotError(f"Symbolic link in archive: {member.name}")

    def _read_metadata(self, tar: tarfile.TarFile) -> SnapshotMetadata:
        """Read and parse metadata.json from tar archive.

        Args:
            tar: Open tarfile to read from.

        Returns:
            Validated SnapshotMetadata.

        Raises:
            InvalidSnapshotError: If metadata is missing or invalid.
        """
        metadata_member = None
        for member in tar.getmembers():
            if member.name.endswith(ArchivePaths.METADATA):
                metadata_member = member
                break

        if metadata_member is None:
            raise InvalidSnapshotError("Archive missing metadata.json")

        f = tar.extractfile(metadata_member)
        if f is None:
            raise InvalidSnapshotError("Cannot read metadata.json")

        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise InvalidSnapshotError(f"Invalid JSON in metadata.json: {e}") from e

        try:
            return validate_metadata(data)
        except ValueError as e:
            raise InvalidSnapshotError(str(e)) from e

    def _validate_file_inventory(
        self,
        tar: tarfile.TarFile,
        metadata: SnapshotMetadata,
    ) -> None:
        """Validate that archive contents match the file inventory.

        Args:
            tar: Open tarfile to validate.
            metadata: Metadata with file inventory.

        Raises:
            InvalidSnapshotError: If files are missing or extra files present.
        """
        # Get actual files in archive (excluding directories)
        actual_files = set()
        for member in tar.getmembers():
            if member.isfile():
                # Extract path relative to archive root
                parts = member.name.split("/", 1)
                if len(parts) > 1:
                    actual_files.add(parts[1])
                else:
                    actual_files.add(member.name)

        # Compare with inventory
        expected_files = set(metadata.files)

        missing = expected_files - actual_files
        if missing:
            logger.warning(f"Files in inventory but not in archive: {missing}")

        extra = actual_files - expected_files
        if extra:
            # Extra files are allowed (forward compatibility)
            logger.debug(f"Extra files in archive not in inventory: {extra}")

    def _merge_parquet_results(
        self,
        archive_path: Path,
        evidence_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge Parquet query results into evidence items.

        Args:
            archive_path: Path to the archive.
            evidence_items: Evidence items to merge into.

        Returns:
            Evidence items with sample_rows populated from Parquet.
        """
        import io

        # Build seq -> evidence item mapping
        seq_map = {item.get("seq"): item for item in evidence_items}

        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".parquet"):
                    # Extract sequence number from filename (e.g., 001-results.parquet)
                    try:
                        filename = member.name.rsplit("/", 1)[-1]
                        seq_str = filename.split("-")[0]
                        seq = int(seq_str)
                    except (ValueError, IndexError):
                        continue

                    if seq not in seq_map:
                        continue

                    # Read Parquet into evidence item
                    f = tar.extractfile(member)
                    if f is not None:
                        try:
                            table = pq.read_table(io.BytesIO(f.read()))
                            rows = table.to_pylist()
                            seq_map[seq]["sample_rows"] = rows
                        except Exception as e:
                            logger.warning(f"Failed to read Parquet file {member.name}: {e}")

        return list(seq_map.values())
