"""Core types for Dataing SDK."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    """Status of an investigation run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class EvidenceKind(str, Enum):
    """Kind of evidence attached to a run."""

    SQL = "sql"
    LOG = "log"
    METRIC = "metric"
    SCHEMA = "schema"
    PIPELINE = "pipeline"
    NOTE = "note"


class AssetRef(BaseModel):
    """Reference to a data asset.

    Aligned with DatasetId from lineage types. The URN format is
    `{platform}://{name}` where:
    - platform: connector type ("postgres", "snowflake", "dbt", etc.)
    - name: fully qualified name ("database.schema.table")

    The datasource_id is separate and never embedded in the URN.
    """

    platform: str = Field(..., description="Data platform (postgres, snowflake, dbt)")
    name: str = Field(..., description="Fully qualified name (db.schema.table)")
    datasource_id: str | None = Field(
        default=None, description="Optional datasource ID for disambiguation"
    )

    def to_urn(self) -> str:
        """Convert to URN string.

        Returns:
            URN in format `{platform}://{name}`.
        """
        return f"{self.platform}://{self.name}"

    @classmethod
    def from_urn(cls, urn: str, datasource_id: str | None = None) -> AssetRef:
        """Parse from URN string.

        Handles formats:
        - "postgres://db.schema.table" (simple)
        - "urn:li:dataset:(urn:li:dataPlatform:snowflake,db.schema.table,PROD)" (DataHub)

        Args:
            urn: URN string to parse.
            datasource_id: Optional datasource ID for disambiguation.

        Returns:
            AssetRef instance.

        Raises:
            ValueError: If URN format is invalid.
        """
        if urn.startswith("urn:li:dataset:"):
            # DataHub format
            parts = urn.split(",")
            platform = parts[0].split(":")[-1]
            name = parts[1] if len(parts) > 1 else ""
            return cls(platform=platform, name=name, datasource_id=datasource_id)
        elif "://" in urn:
            # Simple format
            platform, name = urn.split("://", 1)
            return cls(platform=platform, name=name, datasource_id=datasource_id)
        else:
            raise ValueError(f"Invalid URN format: {urn}")

    def __hash__(self) -> int:
        """Make AssetRef hashable for use in sets."""
        return hash((self.platform, self.name, self.datasource_id))

    def __eq__(self, other: object) -> bool:
        """Check equality."""
        if not isinstance(other, AssetRef):
            return False
        return (
            self.platform == other.platform
            and self.name == other.name
            and self.datasource_id == other.datasource_id
        )


class ResolvedAsset(BaseModel):
    """A resolved asset with datasource binding."""

    asset: AssetRef
    datasource_id: str | None = None
    dataset_id: str = Field(..., description="Canonical URN")
    dataset_type: str | None = Field(
        default=None, description="TABLE, VIEW, MODEL, etc."
    )


class ContextBundle(BaseModel):
    """Snapshot of resolved context (cacheable)."""

    bundle_id: str
    resolved_assets: list[ResolvedAsset] = Field(default_factory=list)
    default_datasource_id: str | None = None
    lineage: dict | None = None
    operational: dict | None = None
    anomalies: list[dict] | None = None
    bundle_hash: str = Field(..., description="Server-derived cache key")
    expires_at: datetime


class Run(BaseModel):
    """An investigation run."""

    run_id: str
    bundle_id: str
    bundle_hash: str
    status: RunStatus
    error_code: str | None = None
    created_at: datetime


class StreamEvent(BaseModel):
    """An SSE stream event."""

    seq: int = Field(..., description="Resume cursor (integer, not UUID)")
    event: str
    run_id: str
    data: dict[str, Any]
    timestamp: datetime


class RunEvidence(BaseModel):
    """Evidence attached to a run."""

    evidence_id: str
    run_id: str
    kind: EvidenceKind
    sql_hash: str | None = None
    source: dict | None = None
    result_summary: str | None = None
    conclusion: str | None = None
    confidence: float | None = None
    linked_assets: list[str] = Field(
        default_factory=list, description="URN strings of linked assets"
    )
