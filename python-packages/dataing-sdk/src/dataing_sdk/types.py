"""Core types for the Dataing SDK.

This module defines the data models used throughout the SDK for representing
assets, runs, evidence, and query results. All models use Pydantic for
validation and serialization.

Key Types:
    - `AssetRef`: Reference to a data asset (table, view, model)
    - `Run`: An investigation run with status tracking
    - `RunEvent`: Real-time event from SSE streaming
    - `ContextBundle`: Cached context snapshot for an asset
    - `QueryResult`: Results from SQL query execution
    - Evidence types: `QueryResultEvidence`, `HypothesisEvidence`, etc.

Example:
    ```python
    from dataing_sdk.types import AssetRef, RunStatus

    # Create an asset reference
    asset = AssetRef(platform="postgres", name="analytics.public.orders")

    # Or parse from URN
    asset = AssetRef.from_urn("postgres://analytics.public.orders")
    ```
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    """Status of an investigation run.

    Investigation runs progress through these states:

    - ``RUNNING``: Investigation is actively executing (gathering context,
      testing hypotheses, executing queries)
    - ``COMPLETED``: Investigation finished successfully with findings
    - ``FAILED``: Investigation encountered an error and stopped
    - ``CANCELLED``: Investigation was manually cancelled by user

    Example:
        ```python
        run = client.run(assets=[...], goal="Why nulls?")
        if run.status == RunStatus.RUNNING:
            print("Investigation in progress...")
        ```
    """

    RUNNING = "running"
    """Investigation is actively executing."""

    COMPLETED = "completed"
    """Investigation finished successfully with findings."""

    FAILED = "failed"
    """Investigation encountered an error and stopped."""

    CANCELLED = "cancelled"
    """Investigation was manually cancelled by user."""


TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class EvidenceKind(str, Enum):
    """Type discriminator for evidence collected during investigations.

    Evidence is the structured output of investigation steps. Each kind has
    a specific schema that enables type-safe rendering and cross-run queries.

    Primary Evidence Types:
        - ``QUERY_RESULT``: SQL query execution with results
        - ``HYPOTHESIS``: Evaluated hypothesis with verdict
        - ``LINEAGE_TRACE``: Data lineage traversal
        - ``SCHEMA_SNAPSHOT``: Table schema at a point in time
        - ``METRIC_CALCULATION``: Calculated data quality metric
        - ``RUN_SUMMARY``: Final investigation synthesis

    Example:
        ```python
        for event in client.stream_run(run.run_id):
            if event.is_evidence:
                kind = event.data.get("kind")
                if kind == EvidenceKind.HYPOTHESIS:
                    print(f"Hypothesis: {event.data['hypothesis_text']}")
        ```
    """

    QUERY_RESULT = "query_result"
    """SQL query was executed; contains sql, row_count, sample_rows."""

    HYPOTHESIS = "hypothesis"
    """Hypothesis was evaluated; contains verdict, confidence, reasoning."""

    LINEAGE_TRACE = "lineage_trace"
    """Lineage was traversed; contains upstream/downstream datasets."""

    SCHEMA_SNAPSHOT = "schema_snapshot"
    """Schema was captured; contains columns, types, nullability."""

    METRIC_CALCULATION = "metric_calculation"
    """Metric was calculated; contains value, expected, deviation."""

    RUN_SUMMARY = "run_summary"
    """Investigation completed; contains root_cause, recommendations."""

    # Legacy values for backward compatibility
    SQL = "sql"
    """Legacy: Use QUERY_RESULT instead."""

    LOG = "log"
    """Legacy: General log entry."""

    METRIC = "metric"
    """Legacy: Use METRIC_CALCULATION instead."""

    SCHEMA = "schema"
    """Legacy: Use SCHEMA_SNAPSHOT instead."""

    PIPELINE = "pipeline"
    """Legacy: Pipeline execution info."""

    NOTE = "note"
    """Legacy: Free-form note."""


class HypothesisVerdict(str, Enum):
    """Verdict from evaluating a hypothesis during investigation.

    When Dataing tests a hypothesis (e.g., "The null spike is channel-specific"),
    it assigns a verdict based on the evidence collected.

    Example:
        ```python
        if evidence.verdict == HypothesisVerdict.ACCEPTED:
            print(f"Root cause found: {evidence.hypothesis_text}")
        ```
    """

    ACCEPTED = "accepted"
    """Hypothesis is supported by evidence with high confidence."""

    REJECTED = "rejected"
    """Evidence contradicts the hypothesis."""

    INCONCLUSIVE = "inconclusive"
    """Insufficient evidence to accept or reject."""


class AssetRef(BaseModel):
    """Reference to a data asset (table, view, model, etc.).

    AssetRef identifies a data asset using a platform and fully-qualified name.
    The URN format is ``{platform}://{name}`` where:

    - **platform**: The data platform type (e.g., "postgres", "snowflake", "dbt")
    - **name**: Fully qualified name (e.g., "database.schema.table")

    The optional ``datasource_id`` disambiguates when multiple datasources
    exist for the same platform. It is never embedded in the URN.

    Attributes:
        platform: Data platform identifier. Common values:
            - ``postgres``, ``snowflake``, ``bigquery``, ``redshift`` (warehouses)
            - ``dbt`` (dbt models)
            - ``s3``, ``gcs`` (object storage)
        name: Fully qualified asset name, typically ``database.schema.table``
            or ``catalog.schema.table`` depending on the platform.
        datasource_id: Optional datasource UUID for disambiguation when
            a tenant has multiple datasources of the same platform type.

    Example:
        ```python
        # Direct construction
        asset = AssetRef(
            platform="postgres",
            name="analytics.public.orders",
            datasource_id="ds-prod-123"
        )

        # Parse from URN string
        asset = AssetRef.from_urn("postgres://analytics.public.orders")

        # Convert back to URN
        urn = asset.to_urn()  # "postgres://analytics.public.orders"

        # DataHub URN format also supported
        asset = AssetRef.from_urn(
            "urn:li:dataset:(urn:li:dataPlatform:snowflake,db.schema.table,PROD)"
        )
        ```

    See Also:
        - `from_urn`: Parse from URN string
        - `to_urn`: Convert to URN string
        - :doc:`/concepts/datasource-resolution`: How datasources are resolved
    """

    platform: str = Field(
        ...,
        description="Data platform (postgres, snowflake, bigquery, dbt, etc.)",
        examples=["postgres", "snowflake", "dbt"],
    )
    name: str = Field(
        ...,
        description="Fully qualified asset name (database.schema.table)",
        examples=["analytics.public.orders", "warehouse.schema.customers"],
    )
    datasource_id: str | None = Field(
        default=None,
        description="Optional datasource UUID for disambiguation",
        examples=["ds-prod-123", "550e8400-e29b-41d4-a716-446655440000"],
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
    dataset_type: str | None = Field(default=None, description="TABLE, VIEW, MODEL, etc.")


class ContextBundle(BaseModel):
    """Cacheable snapshot of resolved context for data assets.

    A ContextBundle contains all the context needed to investigate assets:
    resolved asset references, lineage graphs, operational facts, and
    detected anomalies. Bundles are cached by ``bundle_hash`` to avoid
    redundant context gathering.

    Bundles are created via `DataingClient.create_bundle` or
    `DataingClient.context` and can be reused across multiple
    investigation runs.

    Attributes:
        bundle_id: Unique identifier for this bundle.
        resolved_assets: List of assets with datasource bindings resolved.
        default_datasource_id: The datasource used when not explicitly specified.
        lineage: Data lineage graph (upstream/downstream dependencies).
        operational: Operational facts (freshness, job status, SLAs).
        anomalies: Detected anomalies for the assets.
        bundle_hash: Content-addressable hash for caching (SHA256).
        expires_at: When the cached bundle expires and needs refresh.

    Example:
        ```python
        # Create a bundle for investigation
        bundle = client.create_bundle(
            assets=[AssetRef(platform="postgres", name="db.schema.orders")],
            window="7d"
        )

        print(f"Bundle ID: {bundle.bundle_id}")
        print(f"Hash: {bundle.bundle_hash}")
        print(f"Assets: {len(bundle.resolved_assets)}")

        # Access lineage if available
        if bundle.lineage:
            print(f"Upstream tables: {bundle.lineage.get('upstream', [])}")
        ```
    """

    bundle_id: str = Field(..., description="Unique bundle identifier")
    resolved_assets: list[ResolvedAsset] = Field(
        default_factory=list,
        description="Assets with datasource bindings resolved",
    )
    default_datasource_id: str | None = Field(
        default=None,
        description="Datasource used when not explicitly specified",
    )
    lineage: dict | None = Field(
        default=None,
        description="Data lineage graph (upstream/downstream dependencies)",
    )
    operational: dict | None = Field(
        default=None,
        description="Operational facts (freshness, job status, SLAs)",
    )
    anomalies: list[dict] | None = Field(
        default=None,
        description="Detected anomalies for the assets",
    )
    bundle_hash: str = Field(
        ...,
        description="Content-addressable hash for caching (SHA256)",
    )
    expires_at: datetime = Field(
        ...,
        description="When the cached bundle expires",
    )


class Run(BaseModel):
    """An investigation run that diagnoses data quality issues.

    A Run represents a single investigation execution. It starts in ``RUNNING``
    state and progresses through hypothesis generation, SQL execution, and
    evidence collection until it reaches a terminal state (``COMPLETED``,
    ``FAILED``, or ``CANCELLED``).

    Runs can be monitored via polling (`DataingClient.get_run`) or
    real-time streaming (`DataingClient.stream_run`).

    Attributes:
        run_id: Unique identifier for this run.
        bundle_id: ID of the context bundle used for this run.
        bundle_hash: Content hash of the bundle (for cache invalidation).
        status: Current run status (RUNNING, COMPLETED, FAILED, CANCELLED).
        error_code: Structured error code if failed (e.g., "timeout", "rate_limit").
        created_at: When the run was created.

    Example:
        ```python
        # Start an investigation
        run = client.run(
            assets=[AssetRef(platform="postgres", name="db.schema.orders")],
            goal="Why has the null rate increased from 1% to 15%?"
        )

        print(f"Run ID: {run.run_id}")
        print(f"Status: {run.status}")

        # Poll for completion
        while run.status == RunStatus.RUNNING:
            time.sleep(2)
            run = client.get_run(run.run_id)

        if run.status == RunStatus.COMPLETED:
            print("Investigation complete!")
        elif run.status == RunStatus.FAILED:
            print(f"Failed: {run.error_code}")
        ```

    Note:
        Runs render nicely in Jupyter notebooks via ``_repr_html_()``.
    """

    run_id: str = Field(..., description="Unique run identifier")
    bundle_id: str = Field(..., description="Context bundle used for this run")
    bundle_hash: str = Field(..., description="Content hash for cache invalidation")
    status: RunStatus = Field(..., description="Current run status")
    error_code: str | None = Field(
        default=None,
        description="Structured error code if failed (timeout, rate_limit, etc.)",
    )
    created_at: datetime = Field(..., description="When the run was created")

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
        """  # noqa: E501


class StreamEvent(BaseModel):
    """An SSE stream event."""

    seq: int = Field(..., description="Resume cursor (integer, not UUID)")
    event: str
    run_id: str
    data: dict[str, Any]
    timestamp: datetime


class RunEvent(BaseModel):
    """Real-time event from an investigation run SSE stream.

    RunEvents are emitted during `DataingClient.stream_run` to provide
    live updates on investigation progress. The ``seq`` field enables
    resumption if the connection drops.

    Event Types:
        - ``run_started``: Investigation began
        - ``run_progress``: Progress update (hypothesis being tested, etc.)
        - ``run_evidence``: Evidence collected (query result, hypothesis verdict)
        - ``run_completed``: Investigation finished successfully
        - ``run_failed``: Investigation encountered an error
        - ``run_heartbeat``: Keep-alive signal

    Attributes:
        seq: Sequence number for resumption. Pass to ``last_seq`` to resume.
        event: Event type string (run_started, run_progress, run_evidence, etc.).
        run_id: ID of the run this event belongs to.
        data: Event payload (varies by event type).
        timestamp: ISO 8601 timestamp when the event occurred.

    Example:
        ```python
        for event in client.stream_run(run.run_id):
            print(f"[{event.seq}] {event.event}")

            if event.is_evidence:
                print(f"  Evidence: {event.data.get('kind')}")

            if event.is_terminal:
                print(f"  Final status: {event.event}")
                break

        # Resume from last sequence on reconnection
        for event in client.stream_run(run.run_id, last_seq=last_event.seq):
            ...
        ```

    See Also:
        - `DataingClient.stream_run`: Stream events from a run
        - `is_terminal`: Check if event ends the stream
        - `is_evidence`: Check if event contains evidence
    """

    seq: int = Field(
        ...,
        description="Sequence number for resumption (pass to last_seq)",
    )
    event: str = Field(
        ...,
        description="Event type (run_started, run_progress, run_evidence, etc.)",
    )
    run_id: str = Field(..., description="ID of the run this event belongs to")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Event payload (varies by event type)",
    )
    timestamp: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when the event occurred",
    )

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal event."""
        return self.event in ("run_completed", "run_failed")

    @property
    def is_evidence(self) -> bool:
        """Check if this event contains evidence."""
        return self.event == "run_evidence"

    @property
    def is_progress(self) -> bool:
        """Check if this is a progress event."""
        return self.event == "run_progress"


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
            '<div style="font-family: monospace; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">',  # noqa: E501
            "<strong>Evidence</strong>",
            f'<span style="background: {color}; color: white; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">'  # noqa: E501
            f"{html_module.escape(kind.upper())}"
            f"</span>",
        ]
        if self.confidence is not None:
            parts.append(f" <small>({int(self.confidence * 100)}% confidence)</small>")
        parts.append("<br>")
        if self.result_summary:
            parts.append(f"{html_module.escape(self.result_summary)}<br>")
        if self.conclusion:
            parts.append(f"<strong>Conclusion:</strong> {html_module.escape(self.conclusion)}")
        parts.append("</div>")
        return "".join(parts)


# --- Rich Evidence Types (matching backend schema) ---


class RichEvidenceBase(BaseModel):
    """Base model for rich evidence types with tamper-evidence fields."""

    id: str = Field(..., description="Evidence UUID")
    run_id: str = Field(..., description="Run this evidence belongs to")
    seq: int = Field(..., ge=1, description="Sequence number for ordering")
    kind: EvidenceKind = Field(..., description="Evidence type discriminator")
    timestamp: datetime = Field(..., description="When evidence was created")
    prev_hash: str | None = Field(default=None, description="Hash of previous evidence in chain")
    content_hash: str = Field(..., description="SHA256 hash of content")


class QueryResultEvidence(RichEvidenceBase):
    """Evidence from executing a SQL query."""

    kind: EvidenceKind = EvidenceKind.QUERY_RESULT
    sql: str = Field(..., description="The SQL query executed")
    row_count: int = Field(default=0, description="Number of rows returned")
    columns: list[str] = Field(default_factory=list, description="Column names")
    sample_rows: list[dict[str, Any]] = Field(
        default_factory=list, description="Sample result rows"
    )
    execution_ms: int = Field(default=0, description="Query execution time in ms")
    error: str | None = Field(default=None, description="Error if query failed")


class HypothesisEvidence(RichEvidenceBase):
    """Evidence from evaluating a hypothesis."""

    kind: EvidenceKind = EvidenceKind.HYPOTHESIS
    hypothesis_id: str = Field(..., description="ID of the hypothesis")
    hypothesis_text: str = Field(..., description="The hypothesis statement")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence 0-1")
    supporting_facts: list[str] = Field(default_factory=list, description="Supporting facts")
    verdict: HypothesisVerdict = Field(..., description="Evaluation verdict")
    reasoning: str = Field(default="", description="Explanation of verdict")


class LineageTraceEvidence(RichEvidenceBase):
    """Evidence from lineage traversal."""

    kind: EvidenceKind = EvidenceKind.LINEAGE_TRACE
    root_dataset: str = Field(..., description="Starting dataset")
    upstream: list[str] = Field(default_factory=list, description="Upstream datasets")
    downstream: list[str] = Field(default_factory=list, description="Downstream datasets")
    edges: list[dict[str, str]] = Field(default_factory=list, description="Lineage edges")


class SchemaSnapshotEvidence(RichEvidenceBase):
    """Evidence capturing schema at a point in time."""

    kind: EvidenceKind = EvidenceKind.SCHEMA_SNAPSHOT
    dataset: str = Field(..., description="Dataset name")
    columns: list[dict[str, Any]] = Field(default_factory=list, description="Column definitions")
    row_count: int | None = Field(default=None, description="Approximate row count")
    last_modified: datetime | None = Field(default=None, description="Last modified")


class MetricCalculationEvidence(RichEvidenceBase):
    """Evidence from calculating a metric value."""

    kind: EvidenceKind = EvidenceKind.METRIC_CALCULATION
    metric_name: str = Field(..., description="Name of the metric")
    metric_type: str = Field(..., description="Type of metric")
    value: float = Field(..., description="Calculated value")
    expected_value: float | None = Field(default=None, description="Expected value")
    deviation_pct: float | None = Field(default=None, description="Deviation %")
    dimensions: dict[str, str] = Field(default_factory=dict, description="Dimension values")


class RunSummaryEvidence(RichEvidenceBase):
    """Evidence summarizing the entire run."""

    kind: EvidenceKind = EvidenceKind.RUN_SUMMARY
    root_cause: str | None = Field(default=None, description="Identified root cause")
    confidence: float = Field(default=0.0, description="Confidence in finding")
    recommendations: list[str] = Field(default_factory=list, description="Recommended actions")
    hypotheses_evaluated: int = Field(default=0, description="Hypotheses evaluated")
    queries_executed: int = Field(default=0, description="Queries executed")
    duration_seconds: float = Field(default=0.0, description="Total duration")


class QueryResult(BaseModel):
    """Result from executing a SQL query via the SDK.

    QueryResult is returned by `Context.query` and contains the query
    results along with column metadata and execution statistics.

    Results render as HTML tables in Jupyter notebooks via ``_repr_html_()``.

    Attributes:
        columns: Column metadata with name, type, and nullability.
        rows: Result rows as list of dictionaries (column name -> value).
        row_count: Total number of rows returned.
        truncated: True if results were truncated due to row limits.
        execution_time_ms: Query execution time in milliseconds.

    Example:
        ```python
        ctx = client.context("postgres://db.schema.orders")
        result = ctx.query("SELECT channel, COUNT(*) as cnt FROM orders GROUP BY 1")

        print(f"Returned {result.row_count} rows")
        print(f"Execution time: {result.execution_time_ms}ms")

        for row in result.rows:
            print(f"{row['channel']}: {row['cnt']}")

        # In Jupyter, just display the result for a nice table
        result  # Renders as HTML table
        ```

    Note:
        Results over 50 rows are truncated in the HTML display but all
        rows are available via the ``rows`` attribute.
    """

    columns: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Column metadata (name, type, nullable)",
    )
    rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Result rows as list of {column: value} dicts",
    )
    row_count: int = Field(
        default=0,
        description="Total number of rows returned",
    )
    truncated: bool = Field(
        default=False,
        description="True if results were truncated due to row limits",
    )
    execution_time_ms: int | None = Field(
        default=None,
        description="Query execution time in milliseconds",
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

        col_names = (
            [c.get("name", f"col{i}") for i, c in enumerate(self.columns)]
            if self.columns
            else list(self.rows[0].keys())
        )

        parts = ['<table style="border-collapse: collapse;">']
        parts.append("<thead><tr>")
        for col in col_names:
            parts.append(
                f'<th style="border: 1px solid #ddd; padding: 8px; background: #f5f5f5;">{html_module.escape(str(col))}</th>'  # noqa: E501
            )
        parts.append("</tr></thead>")
        parts.append("<tbody>")
        for row in self.rows[:50]:
            parts.append("<tr>")
            for col in col_names:
                val = row.get(col)
                if val is None:
                    parts.append(
                        '<td style="border: 1px solid #ddd; padding: 8px; color: #999;"><em>NULL</em></td>'  # noqa: E501
                    )
                else:
                    parts.append(
                        f'<td style="border: 1px solid #ddd; padding: 8px;">{html_module.escape(str(val))}</td>'  # noqa: E501
                    )
            parts.append("</tr>")
        parts.append("</tbody></table>")
        if len(self.rows) > 50:
            parts.append(f"<p><em>Showing 50 of {len(self.rows)} rows</em></p>")
        return "".join(parts)


class DiffResult(BaseModel):
    """Result from comparing a metric over a time window.

    DiffResult is returned by `Context.diff` and shows how a metric
    has changed between the current period and a previous period.

    Attributes:
        metric: Name of the metric compared (e.g., "row_count", "null_rate").
        window: Time window for comparison (e.g., "7d", "24h").
        current_value: Current metric value.
        previous_value: Previous period metric value.
        delta: Absolute change (current - previous).
        delta_percent: Percentage change ((current - previous) / previous * 100).
        trend: Direction of change ("up", "down", "stable", or "unknown").
        samples: Time-series data points for visualization.

    Example:
        ```python
        ctx = client.context("postgres://db.schema.orders")
        diff = ctx.diff("null_rate", "7d")

        print(f"Null rate: {diff.current_value:.2%}")
        print(f"Change: {diff.delta_percent:+.1f}% ({diff.trend})")

        if diff.trend == "up" and diff.delta_percent > 100:
            print("WARNING: Significant increase detected!")
        ```
    """

    metric: str = Field(..., description="Name of the metric compared")
    window: str = Field(..., description="Time window for comparison (7d, 24h, etc.)")
    current_value: float | None = Field(default=None, description="Current metric value")
    previous_value: float | None = Field(default=None, description="Previous period value")
    delta: float | None = Field(default=None, description="Absolute change")
    delta_percent: float | None = Field(default=None, description="Percentage change")
    trend: str | None = Field(
        default=None,
        description="Direction: 'up', 'down', 'stable', or 'unknown'",
    )
    samples: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Time-series data points for visualization",
    )


class ExplainResult(BaseModel):
    r"""Natural language explanation of context with insights.

    ExplainResult is returned by `Context.explain` and provides an
    LLM-generated analysis of the assets, lineage, and any anomalies.

    Attributes:
        summary: Natural language explanation of the current state.
        insights: Key observations from analyzing the context.
        recommendations: Suggested actions based on the analysis.
        related_assets: URNs of related assets that may be relevant.

    Example:
        ```python
        ctx = client.context("postgres://db.schema.orders")
        explanation = ctx.explain(focus="anomalies")

        print("Summary:")
        print(explanation.summary)

        print("\nKey Insights:")
        for insight in explanation.insights:
            print(f"  - {insight}")

        print("\nRecommendations:")
        for rec in explanation.recommendations:
            print(f"  - {rec}")
        ```
    """

    summary: str = Field(..., description="Natural language explanation")
    insights: list[str] = Field(
        default_factory=list,
        description="Key observations from analyzing the context",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Suggested actions based on the analysis",
    )
    related_assets: list[str] = Field(
        default_factory=list,
        description="URNs of related assets that may be relevant",
    )


# --- Datasource Types ---


class Datasource(BaseModel):
    """A datasource connection.

    Represents a configured datasource in the Dataing platform.

    Attributes:
        id: Unique datasource identifier.
        name: Human-readable name for the datasource.
        source_type: Type of datasource (postgres, snowflake, bigquery, etc.).
        status: Connection status (connected, disconnected, error).

    Example:
        ```python
        datasources = client.list_datasources()
        for ds in datasources:
            print(f"{ds.name}: {ds.status}")
        ```
    """

    id: str = Field(..., description="Unique datasource identifier")
    name: str = Field(..., description="Human-readable datasource name")
    source_type: str = Field(..., alias="type", description="Type of datasource")
    status: str | None = Field(
        default=None,
        description="Connection status (connected, disconnected, error)",
    )

    model_config = {"populate_by_name": True}


class ConnectionTestResult(BaseModel):
    """Result of testing a datasource connection.

    Returned by `DataingClient.test_datasource` to indicate whether
    a datasource can be reached and queried.

    Attributes:
        success: Whether the connection test succeeded.
        latency_ms: Connection latency in milliseconds (if successful).
        message: Status message (error details if failed, success message otherwise).

    Example:
        ```python
        result = client.test_datasource("ds-prod-123")
        if result.success:
            print(f"Connected in {result.latency_ms}ms")
        else:
            print(f"Failed: {result.message}")
        ```
    """

    success: bool = Field(..., description="Whether the connection test succeeded")
    latency_ms: int | None = Field(
        default=None,
        description="Connection latency in milliseconds",
    )
    message: str | None = Field(
        default=None,
        description="Status message (error details if failed)",
    )


class ColumnSchema(BaseModel):
    """Schema for a table column.

    Attributes:
        name: Column name.
        data_type: Column data type (VARCHAR, INTEGER, etc.).
        nullable: Whether the column allows NULL values.
    """

    name: str = Field(..., description="Column name")
    data_type: str = Field(..., description="Column data type")
    nullable: bool = Field(default=True, description="Whether column allows NULL")


class TableSchema(BaseModel):
    """Schema for a database table.

    Attributes:
        name: Fully qualified table name (schema.table).
        columns: List of column definitions.
    """

    name: str = Field(..., description="Table name")
    columns: list[ColumnSchema] = Field(
        default_factory=list,
        description="Column definitions",
    )


class DatasourceSchema(BaseModel):
    """Schema for a datasource.

    Contains the complete schema information for all tables in a datasource.

    Attributes:
        tables: List of table schemas.

    Example:
        ```python
        schema = client.get_schema("ds-prod-123")
        for table in schema.tables:
            print(f"Table: {table.name}")
            for col in table.columns:
                print(f"  {col.name}: {col.data_type}")
        ```
    """

    tables: list[TableSchema] = Field(
        default_factory=list,
        description="List of table schemas",
    )


# --- Investigation Types ---


class Investigation(BaseModel):
    """An investigation started via the investigations API.

    Attributes:
        investigation_id: Unique identifier for the investigation.
        main_branch_id: ID of the main investigation branch.
        status: Current status (queued, running, completed, failed).
        run_id: Alias for investigation_id (for compatibility with Run type).
    """

    investigation_id: str = Field(..., description="Unique investigation identifier")
    main_branch_id: str = Field(..., description="Main branch identifier")
    status: str = Field(default="queued", description="Current investigation status")

    @property
    def run_id(self) -> str:
        """Alias for investigation_id (compatibility with Run type)."""
        return self.investigation_id

    def _repr_html_(self) -> str:
        """Rich HTML representation for Jupyter notebooks."""
        import html as html_module

        status_colors = {
            "queued": "#f59e0b",
            "running": "#3b82f6",
            "completed": "#10b981",
            "failed": "#ef4444",
            "cancelled": "#6b7280",
        }
        color = status_colors.get(self.status.lower(), "#6b7280")
        return f"""
        <div style="font-family: monospace; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">
            <strong>Investigation</strong>
            <span style="background: {color}20; color: {color}; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">
                {html_module.escape(self.status.upper())}
            </span><br>
            ID: {html_module.escape(self.investigation_id[:16])}...
        </div>
        """  # noqa: E501
