"""Snapshot archive builder for investigation export.

This module provides the SnapshotBuilder class that creates compressed tar.gz
archives from investigation data. Query results are stored as Parquet when
pyarrow is available, falling back to JSON otherwise.
"""

from __future__ import annotations

import io
import json
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dataing.core.exceptions import SnapshotSizeExceededError
from dataing.core.snapshot_schema import (
    SNAPSHOT_SCHEMA_VERSION,
    ArchivePaths,
    ChainMetadata,
    SnapshotMetadata,
)

# Check for optional pyarrow dependency
_HAS_PYARROW = False
try:
    import pyarrow as pa
    import pyarrow.parquet as pq

    _HAS_PYARROW = True
except ImportError:
    pa = None
    pq = None


def has_parquet_support() -> bool:
    """Check if Parquet support is available.

    Returns:
        True if pyarrow is installed, False otherwise.
    """
    return _HAS_PYARROW


class SnapshotBuilder:
    """Build a tar.gz snapshot archive from an investigation.

    Creates a compressed archive following the schema defined in snapshot_schema.py.
    Query results are stored as Parquet for space efficiency when pyarrow is
    available, falling back to JSON otherwise.

    Attributes:
        investigation_id: ID of the investigation being snapshotted.
        max_size_bytes: Maximum allowed archive size (default 100MB).
    """

    def __init__(
        self,
        investigation_id: str,
        max_size_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        """Initialize the SnapshotBuilder.

        Args:
            investigation_id: ID of the investigation to snapshot.
            max_size_bytes: Maximum allowed archive size in bytes.
        """
        self.investigation_id = investigation_id
        self.max_size_bytes = max_size_bytes
        self._files: list[str] = []

    async def build(
        self,
        investigation_state: dict[str, Any],
        evidence_items: list[dict[str, Any]],
        lineage: dict[str, Any] | None = None,
        code_changes: dict[str, Any] | None = None,
        prompts: dict[str, str] | None = None,
    ) -> Path:
        """Build a snapshot archive from investigation data.

        Args:
            investigation_state: Investigation state dict with status, etc.
            evidence_items: List of evidence item dicts ordered by seq.
            lineage: Optional lineage context dict.
            code_changes: Optional code changes dict.
            prompts: Optional dict of prompt names to prompt text.

        Returns:
            Path to the generated .tar.gz archive file.

        Raises:
            SnapshotSizeExceededError: If archive exceeds max_size_bytes.
        """
        self._files = []
        archive_dir = f"snapshot-{self.investigation_id}"

        # Create temp file for the archive
        temp_dir = tempfile.mkdtemp(prefix="dataing-snapshot-")
        archive_path = Path(temp_dir) / f"{archive_dir}.tar.gz"

        with tarfile.open(archive_path, "w:gz") as tar:
            # Write evidence items
            await self._write_evidence(tar, archive_dir, evidence_items)

            # Write lineage
            lineage_data = lineage or {}
            self._add_json_to_tar(tar, archive_dir, ArchivePaths.LINEAGE, lineage_data)

            # Write code changes
            code_changes_data = code_changes or {}
            self._add_json_to_tar(tar, archive_dir, ArchivePaths.CODE_CHANGES, code_changes_data)

            # Write prompts
            await self._write_prompts(tar, archive_dir, prompts)

            # Build and write metadata (must be last to include complete file list)
            metadata = self._build_metadata(investigation_state, evidence_items)
            self._add_json_to_tar(
                tar, archive_dir, ArchivePaths.METADATA, metadata.model_dump(mode="json")
            )

        # Check size
        actual_size = archive_path.stat().st_size
        if actual_size > self.max_size_bytes:
            # Clean up before raising
            archive_path.unlink()
            raise SnapshotSizeExceededError(actual_size, self.max_size_bytes)

        return archive_path

    async def _write_evidence(
        self,
        tar: tarfile.TarFile,
        archive_dir: str,
        evidence_items: list[dict[str, Any]],
    ) -> None:
        """Write evidence items to the archive.

        Args:
            tar: Open tarfile to write to.
            archive_dir: Root directory name in the archive.
            evidence_items: List of evidence item dicts.
        """
        for item in evidence_items:
            seq = item.get("seq", 0)
            kind = item.get("kind", "unknown")

            # Write the evidence item as JSON
            evidence_filename = f"{seq:03d}-{kind}.json"
            evidence_path = f"{ArchivePaths.EVIDENCE_DIR}{evidence_filename}"
            self._add_json_to_tar(tar, archive_dir, evidence_path, item)

            # For query_result with sample_rows, also write Parquet if available
            if kind == "query_result" and "sample_rows" in item:
                sample_rows = item.get("sample_rows", [])
                if sample_rows:
                    parquet_filename = f"{seq:03d}-results.parquet"
                    parquet_path = f"{ArchivePaths.EVIDENCE_DIR}{parquet_filename}"
                    self._write_parquet_or_json(tar, archive_dir, parquet_path, sample_rows)

    def _write_parquet_or_json(
        self,
        tar: tarfile.TarFile,
        archive_dir: str,
        path: str,
        rows: list[dict[str, Any]],
    ) -> None:
        """Write rows as Parquet if available, otherwise JSON.

        Args:
            tar: Open tarfile to write to.
            archive_dir: Root directory name in the archive.
            path: File path within the archive.
            rows: List of row dicts to write.
        """
        if _HAS_PYARROW and rows:
            try:
                # Convert to PyArrow Table and write as Parquet
                table = pa.Table.from_pylist(rows)
                buffer = io.BytesIO()
                pq.write_table(table, buffer)
                data = buffer.getvalue()
                self._add_bytes_to_tar(tar, archive_dir, path, data)
                return
            except Exception:
                # Fall back to JSON on any Parquet error
                pass

        # Fall back to JSON
        json_path = path.replace(".parquet", ".json")
        self._add_json_to_tar(tar, archive_dir, json_path, rows)

    async def _write_prompts(
        self,
        tar: tarfile.TarFile,
        archive_dir: str,
        prompts: dict[str, str] | None,
    ) -> None:
        """Write prompt files to the archive.

        Args:
            tar: Open tarfile to write to.
            archive_dir: Root directory name in the archive.
            prompts: Dict mapping prompt names to prompt text.
        """
        if not prompts:
            return

        prompt_map = {
            "hypothesis": ArchivePaths.PROMPT_HYPOTHESIS,
            "query": ArchivePaths.PROMPT_QUERY,
            "synthesis": ArchivePaths.PROMPT_SYNTHESIS,
        }

        for name, filename in prompt_map.items():
            if name in prompts:
                path = f"{ArchivePaths.PROMPTS_DIR}{filename}"
                self._add_text_to_tar(tar, archive_dir, path, prompts[name])

    def _build_metadata(
        self,
        investigation_state: dict[str, Any],
        evidence_items: list[dict[str, Any]],
    ) -> SnapshotMetadata:
        """Build the snapshot metadata.

        Args:
            investigation_state: Investigation state dict.
            evidence_items: List of evidence items.

        Returns:
            SnapshotMetadata instance.
        """
        # Get root hash from last evidence item if available
        root_hash = None
        if evidence_items:
            last_item = evidence_items[-1]
            root_hash = last_item.get("content_hash")

        # Build chain metadata if we have a hash
        chain_metadata = None
        if root_hash:
            chain_metadata = ChainMetadata()

        return SnapshotMetadata(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            investigation_id=self.investigation_id,
            created_at=datetime.now(UTC),
            source_instance=investigation_state.get("source_instance"),
            tenant_id=investigation_state.get("tenant_id"),
            status=investigation_state.get("status", "unknown"),
            evidence_count=len(evidence_items),
            root_hash=root_hash,
            chain_metadata=chain_metadata,
            max_size_bytes=self.max_size_bytes,
            files=sorted(self._files),
        )

    def _add_json_to_tar(
        self,
        tar: tarfile.TarFile,
        archive_dir: str,
        path: str,
        data: Any,
    ) -> None:
        """Add a JSON file to the tar archive.

        Args:
            tar: Open tarfile to write to.
            archive_dir: Root directory name in the archive.
            path: File path within the archive directory.
            data: Data to serialize as JSON.
        """
        json_bytes = json.dumps(data, indent=2, default=str).encode("utf-8")
        self._add_bytes_to_tar(tar, archive_dir, path, json_bytes)

    def _add_text_to_tar(
        self,
        tar: tarfile.TarFile,
        archive_dir: str,
        path: str,
        text: str,
    ) -> None:
        """Add a text file to the tar archive.

        Args:
            tar: Open tarfile to write to.
            archive_dir: Root directory name in the archive.
            path: File path within the archive directory.
            text: Text content to write.
        """
        self._add_bytes_to_tar(tar, archive_dir, path, text.encode("utf-8"))

    def _add_bytes_to_tar(
        self,
        tar: tarfile.TarFile,
        archive_dir: str,
        path: str,
        data: bytes,
    ) -> None:
        """Add a file to the tar archive from bytes.

        Args:
            tar: Open tarfile to write to.
            archive_dir: Root directory name in the archive.
            path: File path within the archive directory.
            data: Bytes to write.
        """
        full_path = f"{archive_dir}/{path}"
        self._files.append(path)

        info = tarfile.TarInfo(name=full_path)
        info.size = len(data)
        info.mtime = int(datetime.now(UTC).timestamp())

        tar.addfile(info, io.BytesIO(data))
