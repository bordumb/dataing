"""Context object for Dataing SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .exceptions import ValidationError
from .types import (
    AssetRef,
    ContextBundle,
    DiffResult,
    ExplainResult,
    QueryResult,
    ResolvedAsset,
)

if TYPE_CHECKING:
    from .client import DataingClient


class Context:
    """SDK Context object wrapping a ContextBundle.

    Provides access to resolved assets, lineage, and context data.
    Uses server-derived bundle_hash for caching.

    Example:
        ctx = client.context("postgres://db.schema.orders")
        print(ctx.resolved_assets)
        print(ctx.lineage)
    """

    def __init__(self, bundle: ContextBundle, client: DataingClient) -> None:
        """Initialize context from a bundle.

        Args:
            bundle: The underlying ContextBundle.
            client: Parent client for making additional API calls.
        """
        self._bundle = bundle
        self._client = client

    @property
    def bundle_id(self) -> str:
        """Get the bundle ID."""
        return self._bundle.bundle_id

    @property
    def bundle_hash(self) -> str:
        """Get the server-derived bundle hash (cache key)."""
        return self._bundle.bundle_hash

    @property
    def resolved_assets(self) -> list[ResolvedAsset]:
        """Get the per-asset resolution list."""
        return self._bundle.resolved_assets

    @property
    def default_datasource_id(self) -> str | None:
        """Get the default datasource ID."""
        return self._bundle.default_datasource_id

    @property
    def lineage(self) -> dict | None:
        """Get the lineage graph."""
        return self._bundle.lineage

    @property
    def operational(self) -> dict | None:
        """Get operational facts."""
        return self._bundle.operational

    @property
    def anomalies(self) -> list[dict] | None:
        """Get anomaly summaries."""
        return self._bundle.anomalies

    @property
    def assets(self) -> list[AssetRef]:
        """Get the original asset references."""
        return [ra.asset for ra in self._bundle.resolved_assets]

    def __repr__(self) -> str:
        """String representation."""
        asset_count = len(self._bundle.resolved_assets)
        return f"<Context bundle={self.bundle_id[:8]}... assets={asset_count}>"

    def _repr_html_(self) -> str:
        """Rich HTML representation for Jupyter notebooks.

        Returns:
            HTML string for rendering.
        """
        try:
            from dataing_notebook.rendering import render_context

            return render_context(self)
        except ImportError:
            # Fallback if dataing-notebook not installed
            return self._fallback_html()

    def _fallback_html(self) -> str:
        """Fallback HTML when dataing-notebook is not available."""
        import html as html_module

        assets_html = "".join(
            f'<li><code>{html_module.escape(a.dataset_id)}</code></li>'
            for a in self._bundle.resolved_assets
        )
        return f"""
        <div style="font-family: monospace; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">
            <strong>Context</strong><br>
            Bundle: {html_module.escape(self.bundle_id[:16])}...<br>
            Hash: {html_module.escape(self.bundle_hash)}<br>
            <strong>Assets ({len(self._bundle.resolved_assets)}):</strong>
            <ul style="margin: 5px 0;">{assets_html}</ul>
        </div>
        """

    # --- Action methods ---

    def query(
        self,
        sql: str,
        *,
        datasource_id: str | None = None,
        timeout_seconds: int = 30,
        limit: int | None = None,
        offset: int | None = None,
    ) -> QueryResult:
        """Execute a SQL query against the context's datasource.

        Uses the default_datasource_id from the bundle unless overridden.

        Args:
            sql: SQL query to execute.
            datasource_id: Override the default datasource. If not provided,
                uses default_datasource_id from the bundle.
            timeout_seconds: Query timeout in seconds.
            limit: Maximum number of rows to return (pagination).
            offset: Number of rows to skip (pagination).

        Returns:
            QueryResult with columns, rows, and metadata.

        Raises:
            ValidationError: If no datasource_id is available.

        Example:
            ctx = client.context("postgres://db.schema.orders")
            result = ctx.query("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
            print(result.rows)
        """
        ds_id = datasource_id or self.default_datasource_id
        if not ds_id:
            raise ValidationError(
                "No datasource_id available. Either provide datasource_id parameter "
                "or ensure the context bundle has a default_datasource_id."
            )

        # Apply pagination to SQL if provided
        query_sql = sql
        if limit is not None or offset is not None:
            # Basic pagination - most dialects support LIMIT/OFFSET
            if limit is not None:
                query_sql = f"{query_sql.rstrip(';')} LIMIT {limit}"
            if offset is not None:
                query_sql = f"{query_sql} OFFSET {offset}"

        payload = {
            "query": query_sql,
            "timeout_seconds": timeout_seconds,
        }

        response = self._client._request(
            "POST",
            f"/api/v1/datasources/{ds_id}/query",
            json=payload,
        )
        data = response.json()

        return QueryResult(
            columns=data.get("columns", []),
            rows=data.get("rows", []),
            row_count=data.get("row_count", 0),
            truncated=data.get("truncated", False),
            execution_time_ms=data.get("execution_time_ms"),
        )

    async def async_query(
        self,
        sql: str,
        *,
        datasource_id: str | None = None,
        timeout_seconds: int = 30,
        limit: int | None = None,
        offset: int | None = None,
    ) -> QueryResult:
        """Async version of query()."""
        ds_id = datasource_id or self.default_datasource_id
        if not ds_id:
            raise ValidationError(
                "No datasource_id available. Either provide datasource_id parameter "
                "or ensure the context bundle has a default_datasource_id."
            )

        query_sql = sql
        if limit is not None or offset is not None:
            if limit is not None:
                query_sql = f"{query_sql.rstrip(';')} LIMIT {limit}"
            if offset is not None:
                query_sql = f"{query_sql} OFFSET {offset}"

        payload = {
            "query": query_sql,
            "timeout_seconds": timeout_seconds,
        }

        response = await self._client._async_request(
            "POST",
            f"/api/v1/datasources/{ds_id}/query",
            json=payload,
        )
        data = response.json()

        return QueryResult(
            columns=data.get("columns", []),
            rows=data.get("rows", []),
            row_count=data.get("row_count", 0),
            truncated=data.get("truncated", False),
            execution_time_ms=data.get("execution_time_ms"),
        )

    def diff(
        self,
        metric: str,
        window: str = "7d",
        *,
        datasource_id: str | None = None,
    ) -> DiffResult:
        """Compare a metric over a time window.

        Calculates the difference between current and previous values
        for a metric within the specified time window.

        Args:
            metric: Metric to compare (e.g., "row_count", "null_rate").
            window: Time window for comparison (e.g., "7d", "24h", "1w").
            datasource_id: Override the default datasource.

        Returns:
            DiffResult with current/previous values and delta.

        Example:
            ctx = client.context("postgres://db.schema.orders")
            diff = ctx.diff("row_count", "7d")
            print(f"Row count changed by {diff.delta_percent}%")
        """
        ds_id = datasource_id or self.default_datasource_id

        payload: dict[str, Any] = {
            "bundle_id": self.bundle_id,
            "metric": metric,
            "window": window,
        }
        if ds_id:
            payload["datasource_id"] = ds_id

        response = self._client._request(
            "POST",
            "/api/v1/context/diff",
            json=payload,
        )
        data = response.json()

        return DiffResult(
            metric=data.get("metric", metric),
            window=data.get("window", window),
            current_value=data.get("current_value"),
            previous_value=data.get("previous_value"),
            delta=data.get("delta"),
            delta_percent=data.get("delta_percent"),
            trend=data.get("trend"),
            samples=data.get("samples", []),
        )

    async def async_diff(
        self,
        metric: str,
        window: str = "7d",
        *,
        datasource_id: str | None = None,
    ) -> DiffResult:
        """Async version of diff()."""
        ds_id = datasource_id or self.default_datasource_id

        payload: dict[str, Any] = {
            "bundle_id": self.bundle_id,
            "metric": metric,
            "window": window,
        }
        if ds_id:
            payload["datasource_id"] = ds_id

        response = await self._client._async_request(
            "POST",
            "/api/v1/context/diff",
            json=payload,
        )
        data = response.json()

        return DiffResult(
            metric=data.get("metric", metric),
            window=data.get("window", window),
            current_value=data.get("current_value"),
            previous_value=data.get("previous_value"),
            delta=data.get("delta"),
            delta_percent=data.get("delta_percent"),
            trend=data.get("trend"),
            samples=data.get("samples", []),
        )

    def explain(
        self,
        *,
        focus: str | None = None,
    ) -> ExplainResult:
        """Get an AI-powered explanation of the context.

        Analyzes the assets, lineage, and anomalies in the context
        and provides a natural language explanation with insights.

        Args:
            focus: Optional focus area for the explanation
                (e.g., "anomalies", "lineage", "data quality").

        Returns:
            ExplainResult with summary, insights, and recommendations.

        Example:
            ctx = client.context("postgres://db.schema.orders")
            explanation = ctx.explain(focus="anomalies")
            print(explanation.summary)
            for insight in explanation.insights:
                print(f"- {insight}")
        """
        payload: dict[str, Any] = {
            "bundle_id": self.bundle_id,
        }
        if focus:
            payload["focus"] = focus

        response = self._client._request(
            "POST",
            "/api/v1/context/explain",
            json=payload,
        )
        data = response.json()

        return ExplainResult(
            summary=data.get("summary", ""),
            insights=data.get("insights", []),
            recommendations=data.get("recommendations", []),
            related_assets=data.get("related_assets", []),
        )

    async def async_explain(
        self,
        *,
        focus: str | None = None,
    ) -> ExplainResult:
        """Async version of explain()."""
        payload: dict[str, Any] = {
            "bundle_id": self.bundle_id,
        }
        if focus:
            payload["focus"] = focus

        response = await self._client._async_request(
            "POST",
            "/api/v1/context/explain",
            json=payload,
        )
        data = response.json()

        return ExplainResult(
            summary=data.get("summary", ""),
            insights=data.get("insights", []),
            recommendations=data.get("recommendations", []),
            related_assets=data.get("related_assets", []),
        )


def from_sql(
    sql: str,
    *,
    datasource_id: str | None = None,
    default_platform: str | None = None,
    dialect: str | None = None,
    default_database: str | None = None,
    default_schema: str | None = None,
) -> list[AssetRef]:
    """Extract asset references from SQL query.

    Parses SQL to find table references and converts them to AssetRefs.
    Requires either datasource_id or default_platform to be specified.

    Args:
        sql: SQL query to parse.
        datasource_id: Datasource ID to use for all extracted assets.
        default_platform: Platform to use if datasource_id not provided.
        dialect: SQL dialect for parsing (e.g., 'postgres', 'snowflake').
            Defaults to ANSI SQL if not specified.
        default_database: Default database for unqualified table names.
        default_schema: Default schema for unqualified table names.

    Returns:
        List of AssetRef objects for tables referenced in the SQL.

    Raises:
        ValidationError: If neither datasource_id nor default_platform is provided.
        ImportError: If sqlglot is not installed (install with [sql] extra).

    Example:
        assets = from_sql(
            "SELECT * FROM orders JOIN customers ON ...",
            default_platform="postgres",
            default_schema="public"
        )
    """
    if datasource_id is None and default_platform is None:
        raise ValidationError(
            "from_sql requires either datasource_id or default_platform. "
            "Without a platform, we cannot construct valid URNs."
        )

    try:
        import sqlglot
    except ImportError as e:
        raise ImportError(
            "sqlglot is required for from_sql(). "
            "Install with: pip install 'dataing-sdk[sql]'"
        ) from e

    # Parse SQL
    try:
        parsed = sqlglot.parse(sql, dialect=dialect)
    except Exception as e:
        raise ValidationError(f"Failed to parse SQL: {e}") from e

    # Extract table references
    tables: set[str] = set()
    for statement in parsed:
        if statement is None:
            continue
        for table in statement.find_all(sqlglot.exp.Table):
            # Build qualified name
            parts: list[str] = []

            # Database (catalog)
            if table.catalog:
                parts.append(table.catalog)
            elif default_database:
                parts.append(default_database)

            # Schema
            if table.db:
                parts.append(table.db)
            elif default_schema:
                parts.append(default_schema)

            # Table name
            if table.name:
                parts.append(table.name)

            if parts:
                tables.add(".".join(parts))

    # Convert to AssetRefs
    platform = default_platform or "unknown"
    assets: list[AssetRef] = []
    for table_name in sorted(tables):
        assets.append(
            AssetRef(
                platform=platform,
                name=table_name,
                datasource_id=datasource_id,
            )
        )

    return assets
