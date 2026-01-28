"""Investigation snapshot models for state serialization and hydration.

These models capture the complete state of an investigation at a checkpoint,
enabling engineers to reproduce production debugging sessions locally.
"""

from __future__ import annotations

import sys
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from dataing.core.domain_types import LineageContext


class SnapshotCheckpoint(str, Enum):
    """Checkpoints at which snapshots are captured.

    Attributes:
        START: Investigation start, before hypothesis generation.
        HYPOTHESIS_GENERATED: After hypotheses are generated.
        EVIDENCE_COLLECTED: After evidence is collected for a hypothesis.
        COMPLETE: Investigation complete with synthesis.
        FAILED: Investigation failed with error context.
    """

    START = "start"
    HYPOTHESIS_GENERATED = "hypothesis_generated"
    EVIDENCE_COLLECTED = "evidence_collected"
    COMPLETE = "complete"
    FAILED = "failed"


class SampleDataFormat(str, Enum):
    """Format for sample data serialization.

    Attributes:
        PARQUET: Apache Parquet format (preserves dtypes, efficient).
        JSON: JSON format (human-readable, larger size).
        REFERENCE: Reference to external storage (for large datasets).
    """

    PARQUET = "parquet"
    JSON = "json"
    REFERENCE = "reference"


class EnvironmentMetadata(BaseModel):
    """Metadata about the environment where the snapshot was captured.

    Attributes:
        python_version: Python version string (e.g., "3.11.5").
        platform: Platform identifier (e.g., "linux", "darwin").
        dataing_version: Version of the dataing package.
        datasource_type: Type of datasource used.
        package_versions: Versions of key packages for compatibility.
    """

    model_config = ConfigDict(frozen=True)

    python_version: str = Field(default_factory=lambda: sys.version.split()[0])
    platform: str = Field(default_factory=lambda: sys.platform)
    dataing_version: str | None = None
    datasource_type: str | None = None
    package_versions: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def capture_current(cls) -> EnvironmentMetadata:
        """Capture current environment metadata.

        Returns:
            EnvironmentMetadata with current environment details.
        """
        try:
            from importlib.metadata import version

            dataing_ver = version("dataing")
        except Exception:
            dataing_ver = None

        packages: dict[str, str] = {}
        for pkg in ["pydantic", "pandas", "pyarrow", "orjson"]:
            try:
                from importlib.metadata import version as get_version

                packages[pkg] = get_version(pkg)
            except Exception:
                pass

        return cls(
            python_version=sys.version.split()[0],
            platform=sys.platform,
            dataing_version=dataing_ver,
            package_versions=packages,
        )


class SampleDataReference(BaseModel):
    """Reference to sample data stored externally.

    Used when sample data is too large to include inline in the snapshot.

    Attributes:
        table_name: Name of the table this sample is from.
        storage_path: Path to the stored data (e.g., S3 URI, local path).
        format: Format of the stored data.
        row_count: Number of rows in the sample.
        size_bytes: Size of the serialized data in bytes.
        checksum: Optional SHA256 checksum for integrity verification.
    """

    model_config = ConfigDict(frozen=True)

    table_name: str
    storage_path: str
    format: SampleDataFormat
    row_count: int
    size_bytes: int
    checksum: str | None = None


class LineageSnapshot(BaseModel):
    """Snapshot of lineage context at investigation time.

    Captures upstream and downstream dependencies for the investigated asset.

    Attributes:
        target: The target table being investigated.
        upstream: List of upstream tables (data flows from these).
        downstream: List of downstream tables (data flows to these).
        depth: How many hops were captured.
    """

    model_config = ConfigDict(frozen=True)

    target: str
    upstream: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)
    depth: int = 2

    @classmethod
    def from_lineage_context(cls, context: LineageContext | None) -> LineageSnapshot | None:
        """Create LineageSnapshot from LineageContext.

        Args:
            context: The LineageContext to convert.

        Returns:
            LineageSnapshot or None if context is None.
        """
        if context is None:
            return None
        return cls(
            target=context.target,
            upstream=list(context.upstream),
            downstream=list(context.downstream),
        )


class InvestigationSnapshot(BaseModel):
    """Complete snapshot of an investigation at a checkpoint.

    Captures everything needed to reproduce a production debugging session
    locally, including alert context, hypotheses, evidence, schema, and
    sample data.

    Attributes:
        version: Schema version for forward compatibility.
        snapshot_id: Unique identifier for this snapshot.
        investigation_id: ID of the investigation.
        checkpoint: Which checkpoint this snapshot is from.
        captured_at: When the snapshot was captured.
        alert: The anomaly alert that triggered the investigation.
        hypotheses: List of hypotheses generated.
        evidence: List of evidence collected.
        synthesis: Final synthesis result (if complete).
        schema_snapshot: Database schema at investigation time.
        lineage_snapshot: Lineage context at investigation time.
        sample_data_inline: Sample data stored inline (small datasets).
        sample_data_refs: References to externally stored sample data.
        environment: Environment metadata for compatibility checking.
        metadata: Additional custom metadata.
    """

    model_config = ConfigDict(frozen=True)

    # Version for schema evolution
    version: str = "1.0"

    # Identifiers
    snapshot_id: UUID
    investigation_id: UUID
    checkpoint: SnapshotCheckpoint

    # Timestamps
    captured_at: datetime = Field(default_factory=datetime.utcnow)

    # Investigation state (use Any to avoid circular imports in runtime)
    alert: Any = None  # AnomalyAlert
    hypotheses: list[Any] = Field(default_factory=list)  # list[Hypothesis]
    evidence: list[Any] = Field(default_factory=list)  # list[Evidence]
    synthesis: Any | None = None  # SynthesisResponse

    # Context snapshots (use Any to avoid circular imports in runtime)
    schema_snapshot: Any | None = None  # SchemaResponse
    lineage_snapshot: LineageSnapshot | None = None

    # Sample data
    sample_data_inline: dict[str, bytes] = Field(default_factory=dict)
    sample_data_refs: list[SampleDataReference] = Field(default_factory=list)

    # Environment and metadata
    environment: EnvironmentMetadata = Field(default_factory=EnvironmentMetadata.capture_current)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Size limits (configurable)
    max_sample_rows: int = 10000
    max_inline_size_bytes: int = 10 * 1024 * 1024  # 10MB

    def estimated_size_bytes(self) -> int:
        """Estimate the serialized size of this snapshot.

        Returns:
            Estimated size in bytes.
        """
        size = 0

        # Inline sample data
        for data in self.sample_data_inline.values():
            size += len(data)

        # Estimate other fields (rough approximation)
        # Alert, hypotheses, evidence, synthesis, schema - estimate ~1KB each
        size += 1024  # alert
        size += len(self.hypotheses) * 512  # hypotheses
        size += len(self.evidence) * 2048  # evidence (includes query results)
        if self.synthesis:
            size += 2048
        if self.schema_snapshot:
            size += 4096  # schema can be large

        return size

    def is_oversized(self) -> bool:
        """Check if snapshot exceeds recommended size limits.

        Returns:
            True if snapshot is larger than max_inline_size_bytes.
        """
        return self.estimated_size_bytes() > self.max_inline_size_bytes

    def get_sample_table_names(self) -> list[str]:
        """Get names of all tables with sample data.

        Returns:
            List of table names with sample data available.
        """
        inline_tables = list(self.sample_data_inline.keys())
        ref_tables = [ref.table_name for ref in self.sample_data_refs]
        return inline_tables + ref_tables
