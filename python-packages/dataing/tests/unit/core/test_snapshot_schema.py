"""Unit tests for snapshot archive schema."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dataing.core.snapshot_schema import (
    SNAPSHOT_SCHEMA_VERSION,
    ArchivePaths,
    ChainMetadata,
    SnapshotMetadata,
    json_schema,
    validate_metadata,
)

# ---------------------------------------------------------------------------
# SNAPSHOT_SCHEMA_VERSION
# ---------------------------------------------------------------------------


class TestSnapshotSchemaVersion:
    """Tests for schema version constant."""

    def test_version_is_string(self) -> None:
        """Version is a string."""
        assert isinstance(SNAPSHOT_SCHEMA_VERSION, str)

    def test_version_is_1_0(self) -> None:
        """Initial version is 1.0."""
        assert SNAPSHOT_SCHEMA_VERSION == "1.0"


# ---------------------------------------------------------------------------
# ArchivePaths
# ---------------------------------------------------------------------------


class TestArchivePaths:
    """Tests for archive path constants."""

    def test_metadata_path(self) -> None:
        """Metadata file at root."""
        assert ArchivePaths.METADATA == "metadata.json"

    def test_evidence_dir(self) -> None:
        """Evidence directory with trailing slash."""
        assert ArchivePaths.EVIDENCE_DIR == "evidence/"

    def test_lineage_path(self) -> None:
        """Lineage file at root."""
        assert ArchivePaths.LINEAGE == "lineage.json"

    def test_code_changes_path(self) -> None:
        """Code changes file at root."""
        assert ArchivePaths.CODE_CHANGES == "code_changes.json"

    def test_prompts_dir(self) -> None:
        """Prompts directory with trailing slash."""
        assert ArchivePaths.PROMPTS_DIR == "prompts/"

    def test_prompt_files(self) -> None:
        """Prompt file names."""
        assert ArchivePaths.PROMPT_HYPOTHESIS == "hypothesis.txt"
        assert ArchivePaths.PROMPT_QUERY == "query.txt"
        assert ArchivePaths.PROMPT_SYNTHESIS == "synthesis.txt"

    def test_paths_match_epic_spec(self) -> None:
        """Paths match the documented archive structure."""
        # From epic spec:
        # snapshot-<id>/
        #   metadata.json
        #   evidence/
        #   lineage.json
        #   code_changes.json
        #   prompts/
        assert ArchivePaths.METADATA == "metadata.json"
        assert ArchivePaths.EVIDENCE_DIR.startswith("evidence")
        assert ArchivePaths.LINEAGE == "lineage.json"
        assert ArchivePaths.CODE_CHANGES == "code_changes.json"
        assert ArchivePaths.PROMPTS_DIR.startswith("prompts")


# ---------------------------------------------------------------------------
# SnapshotMetadata
# ---------------------------------------------------------------------------


class TestSnapshotMetadata:
    """Tests for SnapshotMetadata model."""

    def test_required_fields(self) -> None:
        """Model requires investigation_id, status, evidence_count."""
        metadata = SnapshotMetadata(
            investigation_id="inv-123",
            status="complete",
            evidence_count=5,
        )
        assert metadata.investigation_id == "inv-123"
        assert metadata.status == "complete"
        assert metadata.evidence_count == 5

    def test_schema_version_default(self) -> None:
        """schema_version defaults to SNAPSHOT_SCHEMA_VERSION."""
        metadata = SnapshotMetadata(
            investigation_id="inv-123",
            status="complete",
            evidence_count=0,
        )
        assert metadata.schema_version == "1.0"
        assert metadata.schema_version == SNAPSHOT_SCHEMA_VERSION

    def test_max_size_bytes_default(self) -> None:
        """max_size_bytes defaults to 100MB."""
        metadata = SnapshotMetadata(
            investigation_id="inv-123",
            status="complete",
            evidence_count=0,
        )
        assert metadata.max_size_bytes == 100 * 1024 * 1024

    def test_files_default_empty_list(self) -> None:
        """Files defaults to empty list."""
        metadata = SnapshotMetadata(
            investigation_id="inv-123",
            status="complete",
            evidence_count=0,
        )
        assert metadata.files == []

    def test_optional_fields(self) -> None:
        """Optional fields can be None or omitted."""
        metadata = SnapshotMetadata(
            investigation_id="inv-123",
            status="complete",
            evidence_count=0,
        )
        assert metadata.source_instance is None
        assert metadata.tenant_id is None
        assert metadata.root_hash is None
        assert metadata.chain_metadata is None

    def test_all_fields(self) -> None:
        """Model accepts all fields."""
        now = datetime.now(UTC)
        chain_meta = ChainMetadata(algorithm="sha256", domain_prefix="evidence_v1:")
        metadata = SnapshotMetadata(
            schema_version="1.0",
            investigation_id="inv-123",
            created_at=now,
            source_instance="https://dataing.example.com",
            tenant_id="tenant-456",
            status="complete",
            evidence_count=10,
            root_hash="abc123" + "0" * 58,
            chain_metadata=chain_meta,
            max_size_bytes=50 * 1024 * 1024,
            files=["metadata.json", "evidence/001-query.json"],
        )
        assert metadata.schema_version == "1.0"
        assert metadata.investigation_id == "inv-123"
        assert metadata.created_at == now
        assert metadata.source_instance == "https://dataing.example.com"
        assert metadata.tenant_id == "tenant-456"
        assert metadata.status == "complete"
        assert metadata.evidence_count == 10
        assert metadata.root_hash == "abc123" + "0" * 58
        assert metadata.chain_metadata == chain_meta
        assert metadata.max_size_bytes == 50 * 1024 * 1024
        assert len(metadata.files) == 2

    def test_evidence_count_must_be_non_negative(self) -> None:
        """evidence_count must be >= 0."""
        with pytest.raises(ValueError):
            SnapshotMetadata(
                investigation_id="inv-123",
                status="complete",
                evidence_count=-1,
            )

    def test_frozen(self) -> None:
        """Model is frozen (immutable)."""
        metadata = SnapshotMetadata(
            investigation_id="inv-123",
            status="complete",
            evidence_count=0,
        )
        with pytest.raises(ValidationError):
            metadata.investigation_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ChainMetadata
# ---------------------------------------------------------------------------


class TestChainMetadata:
    """Tests for ChainMetadata model."""

    def test_defaults(self) -> None:
        """Default values match evidence module conventions."""
        chain_meta = ChainMetadata()
        assert chain_meta.algorithm == "sha256"
        assert chain_meta.domain_prefix == "evidence_v1:"

    def test_custom_values(self) -> None:
        """Custom values can be set."""
        chain_meta = ChainMetadata(algorithm="sha3-256", domain_prefix="custom:")
        assert chain_meta.algorithm == "sha3-256"
        assert chain_meta.domain_prefix == "custom:"


# ---------------------------------------------------------------------------
# validate_metadata
# ---------------------------------------------------------------------------


class TestValidateMetadata:
    """Tests for validate_metadata function."""

    def test_valid_minimal(self) -> None:
        """Validates minimal valid data."""
        data = {
            "investigation_id": "inv-123",
            "status": "complete",
            "evidence_count": 5,
        }
        metadata = validate_metadata(data)
        assert metadata.investigation_id == "inv-123"
        assert metadata.status == "complete"
        assert metadata.evidence_count == 5

    def test_valid_full(self) -> None:
        """Validates complete data."""
        data = {
            "schema_version": "1.0",
            "investigation_id": "inv-456",
            "created_at": "2024-01-15T10:30:00Z",
            "source_instance": "https://example.com",
            "tenant_id": "tenant-789",
            "status": "in_progress",
            "evidence_count": 10,
            "root_hash": "a" * 64,
            "chain_metadata": {"algorithm": "sha256", "domain_prefix": "evidence_v1:"},
            "max_size_bytes": 50000000,
            "files": ["metadata.json", "evidence/001.json"],
        }
        metadata = validate_metadata(data)
        assert metadata.investigation_id == "inv-456"
        assert metadata.evidence_count == 10
        assert metadata.chain_metadata is not None
        assert metadata.chain_metadata.algorithm == "sha256"

    def test_missing_required_field(self) -> None:
        """Raises ValueError for missing required fields."""
        data = {
            "status": "complete",
            "evidence_count": 5,
            # missing investigation_id
        }
        with pytest.raises(ValueError, match="Invalid snapshot metadata"):
            validate_metadata(data)

    def test_invalid_evidence_count(self) -> None:
        """Raises ValueError for invalid evidence_count."""
        data = {
            "investigation_id": "inv-123",
            "status": "complete",
            "evidence_count": "not-a-number",
        }
        with pytest.raises(ValueError, match="Invalid snapshot metadata"):
            validate_metadata(data)

    def test_rejects_invalid_data(self) -> None:
        """Raises ValueError for completely invalid data."""
        with pytest.raises(ValueError, match="Invalid snapshot metadata"):
            validate_metadata({"random": "data"})


# ---------------------------------------------------------------------------
# json_schema
# ---------------------------------------------------------------------------


class TestJsonSchema:
    """Tests for json_schema function."""

    def test_returns_dict(self) -> None:
        """Returns a dict."""
        schema = json_schema()
        assert isinstance(schema, dict)

    def test_has_schema_keys(self) -> None:
        """Has standard JSON Schema keys."""
        schema = json_schema()
        assert "properties" in schema
        assert "required" in schema
        assert "type" in schema

    def test_type_is_object(self) -> None:
        """Root type is object."""
        schema = json_schema()
        assert schema["type"] == "object"

    def test_required_fields_in_schema(self) -> None:
        """Required fields are listed."""
        schema = json_schema()
        required = schema["required"]
        assert "investigation_id" in required
        assert "status" in required
        assert "evidence_count" in required

    def test_properties_include_all_fields(self) -> None:
        """All model fields are in properties."""
        schema = json_schema()
        props = schema["properties"]
        expected_fields = [
            "schema_version",
            "investigation_id",
            "created_at",
            "source_instance",
            "tenant_id",
            "status",
            "evidence_count",
            "root_hash",
            "chain_metadata",
            "max_size_bytes",
            "files",
        ]
        for field in expected_fields:
            assert field in props, f"Missing field: {field}"

    def test_schema_is_json_serializable(self) -> None:
        """Schema can be serialized to JSON."""
        import json

        schema = json_schema()
        json_str = json.dumps(schema)
        assert len(json_str) > 100  # Non-trivial output
