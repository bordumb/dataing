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

    def _repr_html_(self) -> str:
        """Rich HTML representation for Jupyter notebooks."""
        try:
            from dataing_notebook.rendering import render_run

            return render_run(self)
        except ImportError:
            return self._fallback_html()

    def _fallback_html(self) -> str:
        """Fallback HTML when dataing-notebook is not available."""
        import html as html_module

        status_colors = {
            "running": "#3b82f6",
            "completed": "#10b981",
            "failed": "#ef4444",
            "cancelled": "#6b7280",
        }
        status = self.status.value if hasattr(self.status, "value") else str(self.status)
        color = status_colors.get(status.lower(), "#6b7280")
        return f"""
        <div style="font-family: monospace; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">
            <strong>Run</strong>
            <span style="background: {color}20; color: {color}; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">
                {html_module.escape(status.upper())}
            </span><br>
            ID: {html_module.escape(self.run_id[:16])}...<br>
            Bundle Hash: {html_module.escape(self.bundle_hash)}
        </div>
        """


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

    def _repr_html_(self) -> str:
        """Rich HTML representation for Jupyter notebooks."""
        try:
            from dataing_notebook.rendering import render_evidence

            return render_evidence(self)
        except ImportError:
            return self._fallback_html()

    def _fallback_html(self) -> str:
        """Fallback HTML when dataing-notebook is not available."""
        import html as html_module

        kind = self.kind.value if hasattr(self.kind, "value") else str(self.kind)
        kind_colors = {
            "sql": "#8b5cf6",
            "metric": "#10b981",
            "schema": "#f59e0b",
            "log": "#6b7280",
            "pipeline": "#3b82f6",
            "note": "#ec4899",
        }
        color = kind_colors.get(kind.lower(), "#6b7280")

        parts = [
            f'<div style="font-family: monospace; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">',
            f'<strong>Evidence</strong>',
            f'<span style="background: {color}; color: white; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">'
            f'{html_module.escape(kind.upper())}'
            f'</span>',
        ]
        if self.confidence is not None:
            parts.append(f' <small>({int(self.confidence * 100)}% confidence)</small>')
        parts.append('<br>')
        if self.result_summary:
            parts.append(f'{html_module.escape(self.result_summary)}<br>')
        if self.conclusion:
            parts.append(f'<strong>Conclusion:</strong> {html_module.escape(self.conclusion)}')
        parts.append('</div>')
        return ''.join(parts)


class QueryResult(BaseModel):
    """Result of a SQL query execution."""

    columns: list[dict[str, Any]] = Field(
        default_factory=list, description="Column metadata"
    )
    rows: list[dict[str, Any]] = Field(default_factory=list, description="Result rows")
    row_count: int = Field(default=0, description="Number of rows returned")
    truncated: bool = Field(
        default=False, description="Whether results were truncated"
    )
    execution_time_ms: int | None = Field(
        default=None, description="Query execution time in milliseconds"
    )

    def _repr_html_(self) -> str:
        """Rich HTML representation for Jupyter notebooks."""
        try:
            from dataing_notebook.rendering import render_table

            return render_table(self.rows, self.columns)
        except ImportError:
            return self._fallback_html()

    def _fallback_html(self) -> str:
        """Fallback HTML when dataing-notebook is not available."""
        import html as html_module

        if not self.rows:
            return "<p><em>No data</em></p>"

        col_names = [c.get("name", f"col{i}") for i, c in enumerate(self.columns)] if self.columns else list(self.rows[0].keys())

        parts = ['<table style="border-collapse: collapse;">']
        parts.append('<thead><tr>')
        for col in col_names:
            parts.append(f'<th style="border: 1px solid #ddd; padding: 8px; background: #f5f5f5;">{html_module.escape(str(col))}</th>')
        parts.append('</tr></thead>')
        parts.append('<tbody>')
        for row in self.rows[:50]:
            parts.append('<tr>')
            for col in col_names:
                val = row.get(col)
                if val is None:
                    parts.append('<td style="border: 1px solid #ddd; padding: 8px; color: #999;"><em>NULL</em></td>')
                else:
                    parts.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{html_module.escape(str(val))}</td>')
            parts.append('</tr>')
        parts.append('</tbody></table>')
        if len(self.rows) > 50:
            parts.append(f'<p><em>Showing 50 of {len(self.rows)} rows</em></p>')
        return ''.join(parts)


class DiffResult(BaseModel):
    """Result of a metric diff operation."""

    metric: str
    window: str
    current_value: float | None = None
    previous_value: float | None = None
    delta: float | None = None
    delta_percent: float | None = None
    trend: str | None = Field(
        default=None, description="up, down, stable, or unknown"
    )
    samples: list[dict[str, Any]] = Field(
        default_factory=list, description="Time-series samples"
    )


class ExplainResult(BaseModel):
    """Result of an explain operation."""

    summary: str = Field(..., description="Natural language explanation")
    insights: list[str] = Field(
        default_factory=list, description="Key insights discovered"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Recommended actions"
    )
    related_assets: list[str] = Field(
        default_factory=list, description="URNs of related assets"
    )
