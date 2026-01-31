"""Snapshot archive schema for investigation export and import.

This module defines the canonical snapshot archive directory layout and the
metadata schema for portable investigation snapshots. The schema is designed
for forward compatibility and integrity verification.

Archive Structure
-----------------
snapshot-<id>/
  metadata.json         # Investigation metadata and file manifest
  evidence/
    001-hypothesis.json # Evidence items by sequence number
    002-query.json
    003-results.parquet # Query results in Parquet format
    ...
  lineage.json          # Lineage context at investigation time
  code_changes.json     # Related code changes (requires git integration)
  prompts/
    hypothesis.txt      # Agent prompts used during investigation
    query.txt
    synthesis.txt

The metadata.json file contains versioning, provenance, and a file manifest
that enables importers to validate archive completeness.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Schema version for forward compatibility.
# Increment minor version for additive changes, major version for breaking changes.
SNAPSHOT_SCHEMA_VERSION = "1.0"

# Supported schema versions for import.
# Add new versions here as they are released.
SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0"})


class InvalidSnapshotError(Exception):
    """Snapshot archive is invalid or malformed.

    Raised when a snapshot archive cannot be read or is missing required files.
    """

    pass


class UnsupportedSchemaVersionError(Exception):
    """Snapshot schema version is not supported.

    Raised when importing a snapshot with a schema version that is not in
    SUPPORTED_SCHEMA_VERSIONS. This typically means the snapshot was created
    with a newer version of Dataing.

    Attributes:
        version: The unsupported schema version.
        supported: Set of supported versions.
    """

    def __init__(self, version: str, supported: frozenset[str] | None = None) -> None:
        """Initialize UnsupportedSchemaVersionError.

        Args:
            version: The unsupported schema version.
            supported: Set of supported versions.
        """
        supported = supported or SUPPORTED_SCHEMA_VERSIONS
        super().__init__(
            f"Schema version '{version}' is not supported. "
            f"Supported versions: {', '.join(sorted(supported))}. "
            "Please upgrade Dataing to import this snapshot."
        )
        self.version = version
        self.supported = supported


class ArchivePaths:
    """Well-known paths within a snapshot archive.

    These constants define the canonical structure of a snapshot archive.
    All paths are relative to the archive root directory.
    """

    METADATA = "metadata.json"
    EVIDENCE_DIR = "evidence/"
    LINEAGE = "lineage.json"
    CODE_CHANGES = "code_changes.json"
    PROMPTS_DIR = "prompts/"

    # Prompt file names within PROMPTS_DIR
    PROMPT_HYPOTHESIS = "hypothesis.txt"
    PROMPT_QUERY = "query.txt"
    PROMPT_SYNTHESIS = "synthesis.txt"


class ChainMetadata(BaseModel):
    """Hash chain metadata for tamper-evident snapshots.

    Captures the state of the evidence hash chain at export time.
    """

    model_config = ConfigDict(frozen=True)

    algorithm: str = Field(default="sha256", description="Hash algorithm used")
    domain_prefix: str = Field(default="evidence_v1:", description="Domain separation prefix")


class SnapshotMetadata(BaseModel):
    """Metadata for a snapshot archive.

    This model is serialized to metadata.json at the root of every snapshot
    archive. It contains versioning information, provenance data, and a
    complete file manifest for integrity verification.

    Attributes:
        schema_version: Version of the snapshot schema for forward compatibility.
        investigation_id: ID of the investigation being snapshotted.
        created_at: When the snapshot was created.
        source_instance: URL of the originating Dataing server (optional).
        tenant_id: Tenant ID (stripped on cross-tenant import for EE).
        status: Investigation status at export time.
        evidence_count: Number of evidence items in the archive.
        root_hash: Final hash in the evidence chain (from fn-33).
        chain_metadata: Hash chain algorithm metadata.
        max_size_bytes: Maximum allowed archive size.
        files: Relative paths of all files in the archive.
    """

    model_config = ConfigDict(frozen=True)

    # Schema version for forward compatibility
    schema_version: str = Field(
        default=SNAPSHOT_SCHEMA_VERSION,
        description="Snapshot schema version for forward compatibility",
    )

    # Investigation identification
    investigation_id: str = Field(..., description="ID of the investigation")

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the snapshot was created",
    )

    # Provenance
    source_instance: str | None = Field(
        default=None, description="URL of the originating Dataing server"
    )
    tenant_id: str | None = Field(
        default=None, description="Tenant ID (stripped on cross-tenant import)"
    )

    # Investigation state at export
    status: str = Field(..., description="Investigation status at export time")

    # Evidence chain
    evidence_count: int = Field(..., ge=0, description="Number of evidence items in the archive")
    root_hash: str | None = Field(
        default=None,
        description="Final hash in the evidence chain for integrity verification",
    )
    chain_metadata: ChainMetadata | None = Field(
        default=None, description="Hash chain algorithm metadata"
    )

    # Size limits
    max_size_bytes: int = Field(
        default=100 * 1024 * 1024,
        description="Maximum allowed archive size in bytes (default 100MB)",
    )

    # File manifest
    files: list[str] = Field(
        default_factory=list,
        description="Relative paths of all files in the archive for completeness check",
    )


def validate_metadata(data: dict[str, Any]) -> SnapshotMetadata:
    """Parse and validate incoming JSON data against the SnapshotMetadata schema.

    Args:
        data: Dictionary parsed from metadata.json.

    Returns:
        Validated SnapshotMetadata instance.

    Raises:
        ValueError: If the data is invalid or missing required fields.
    """
    try:
        return SnapshotMetadata.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Invalid snapshot metadata: {e}") from e


def json_schema() -> dict[str, Any]:
    """Generate JSON Schema for external tooling validation.

    Returns:
        JSON Schema dict compatible with JSON Schema Draft 2020-12.
    """
    return SnapshotMetadata.model_json_schema()
