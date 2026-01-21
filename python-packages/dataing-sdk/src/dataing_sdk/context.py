"""Context object for interacting with resolved data assets.

The `Context` class is the primary interface for working with data assets
after they have been resolved by the Dataing API. It wraps a
`dataing_sdk.types.ContextBundle` and provides convenient methods for:

- **Querying**: Execute SQL queries against the context's datasource
- **Diffing**: Compare metrics over time windows
- **Explaining**: Get AI-powered insights about the data

Context objects are created via `DataingClient.context` and support rich
display in Jupyter notebooks.

Example:
    Basic usage:

    ```python
    from dataing_sdk import DataingClient

    client = DataingClient()
    ctx = client.context("postgres://analytics.public.orders")

    # Access resolved assets
    for asset in ctx.resolved_assets:
        print(f"Dataset: {asset.dataset_id}")

    # Query the data
    result = ctx.query("SELECT COUNT(*) as total FROM orders")
    print(f"Total orders: {result.rows[0]['total']}")

    # Compare metrics over time
    diff = ctx.diff("row_count", window="7d")
    if diff.delta_percent and diff.delta_percent < -10:
        print(f"Warning: Row count dropped {abs(diff.delta_percent)}%")
    ```

See Also:
    - `DataingClient.context`: Create a Context from URNs or AssetRefs
    - `dataing_sdk.types.ContextBundle`: The underlying data structure
    - `from_sql`: Extract asset references from SQL queries
"""

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

    The Context class provides a rich interface for working with resolved data
    assets. It wraps a server-side `dataing_sdk.types.ContextBundle`
    and adds methods for querying, comparing, and analyzing data.

    Context objects are created via `DataingClient.context` and should
    not be instantiated directly. They support rich display in Jupyter notebooks
    via ``_repr_html_``.

    Attributes:
        bundle_id: Unique identifier for the underlying bundle.
        bundle_hash: Content-based hash used for caching. Two bundles with
            the same assets will have the same hash.
        resolved_assets: List of resolved asset metadata including schemas
            and statistics.
        default_datasource_id: The datasource ID used for queries if not
            overridden.
        lineage: Upstream and downstream lineage graph (if requested).
        operational: Operational metadata like job runs and freshness.
        anomalies: List of detected anomalies for the assets.
        assets: The original `dataing_sdk.types.AssetRef` objects.

    Example:
        Accessing context properties:

        ```python
        ctx = client.context("postgres://db.schema.orders")

        # Check what was resolved
        print(f"Bundle: {ctx.bundle_id}")
        print(f"Hash: {ctx.bundle_hash}")

        for asset in ctx.resolved_assets:
            print(f"  - {asset.dataset_id}: {len(asset.columns)} columns")

        # Access lineage if available
        if ctx.lineage:
            print(f"Upstream: {ctx.lineage.get('upstream', [])}")
        ```

        Querying and analyzing:

        ```python
        # Execute SQL
        result = ctx.query("SELECT * FROM orders LIMIT 10")

        # Compare metrics
        diff = ctx.diff("null_rate", window="7d")

        # Get AI explanation
        explanation = ctx.explain(focus="anomalies")
        print(explanation.summary)
        ```

    Note:
        Context objects hold a reference to the parent
        `dataing_sdk.client.DataingClient` for making API calls.
        Ensure the client remains open while using the context.

    See Also:
        - `DataingClient.context`: Create contexts from URNs
        - `dataing_sdk.types.ContextBundle`: The underlying data
    """

    def __init__(self, bundle: ContextBundle, client: DataingClient) -> None:
        """Initialize context from a bundle.

        This constructor is called internally by `DataingClient.context`.
        Users should not instantiate Context objects directly.

        Args:
            bundle: The underlying `dataing_sdk.types.ContextBundle`
                containing resolved asset data.
            client: Parent `dataing_sdk.client.DataingClient` instance
                for making API calls (query, diff, explain).
        """
        self._bundle = bundle
        self._client = client

    @property
    def bundle_id(self) -> str:
        """Get the unique bundle identifier.

        The bundle_id is a server-generated UUID that uniquely identifies
        this context bundle instance.
        """
        return self._bundle.bundle_id

    @property
    def bundle_hash(self) -> str:
        """Get the content-based bundle hash.

        The bundle_hash is derived from the bundle contents and can be used
        as a cache key. Two bundles with the same assets will produce the
        same hash, enabling efficient caching and deduplication.
        """
        return self._bundle.bundle_hash

    @property
    def resolved_assets(self) -> list[ResolvedAsset]:
        """Get the list of resolved assets with full metadata.

        Each `dataing_sdk.types.ResolvedAsset` contains the original
        asset reference plus resolved information like ``dataset_id``, column
        schemas, and statistics.
        """
        return self._bundle.resolved_assets

    @property
    def default_datasource_id(self) -> str | None:
        """Get the default datasource ID for queries.

        If set, this datasource is used for `query`, `diff`,
        and other operations unless explicitly overridden. Returns ``None``
        if no default was determined during bundle creation.
        """
        return self._bundle.default_datasource_id

    @property
    def lineage(self) -> dict | None:
        """Get the lineage graph if available.

        Contains upstream and downstream dependencies extracted from
        configured lineage providers (dbt, DataHub, etc.). Returns ``None``
        if lineage was not requested or not available.

        The structure typically includes ``upstream`` and ``downstream`` lists
        of related dataset identifiers.
        """
        return self._bundle.lineage

    @property
    def operational(self) -> dict | None:
        """Get operational metadata if available.

        Contains information about job runs, data freshness, and other
        operational facts from the data platform. Returns ``None`` if
        operational data was not requested or not available.
        """
        return self._bundle.operational

    @property
    def anomalies(self) -> list[dict] | None:
        """Get detected anomalies for the assets.

        Lists anomalies detected by configured monitoring systems. Each
        anomaly dict typically contains ``type``, ``severity``, ``message``,
        and ``detected_at`` fields. Returns ``None`` if anomalies were
        not requested or not available.
        """
        return self._bundle.anomalies

    @property
    def assets(self) -> list[AssetRef]:
        """Get the original asset references.

        Returns the `dataing_sdk.types.AssetRef` objects that were
        used to create this context. Useful for passing to `DataingClient.run`.
        """
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

        Runs a read-only SQL query through the Dataing query proxy. The query
        is executed against the datasource associated with this context, with
        built-in safety checks and timeout handling.

        Queries are executed in a sandboxed environment:

        - Read-only: Write operations are blocked
        - Timeout-protected: Long queries are cancelled
        - Logged: All queries are recorded for audit

        Args:
            sql: SQL query to execute. Should be a SELECT statement.
                The query is executed as-is, so ensure proper quoting
                and escaping.
            datasource_id: Override the default datasource. If not provided,
                uses `default_datasource_id` from the bundle.
            timeout_seconds: Maximum query execution time in seconds.
                Queries exceeding this limit are cancelled.
            limit: Maximum number of rows to return. Added as ``LIMIT N``
                clause to the query.
            offset: Number of rows to skip. Added as ``OFFSET N`` clause.
                Requires ``limit`` to be effective in most databases.

        Returns:
            A `dataing_sdk.types.QueryResult` containing columns,
            rows, row count, and execution metadata.

        Raises:
            ValidationError: If no datasource is available (neither explicit
                nor default).
            AuthError: If not authorized to query this datasource.
            ServerError: If query execution fails.

        Example:
            Basic query:

            ```python
            ctx = client.context("postgres://analytics.public.orders")
            result = ctx.query("SELECT status, COUNT(*) as cnt FROM orders GROUP BY status")

            for row in result.rows:
                print(f"{row['status']}: {row['cnt']}")
            ```

            With pagination:

            ```python
            # Page through results
            page = 0
            page_size = 100
            while True:
                result = ctx.query(
                    "SELECT * FROM orders ORDER BY created_at DESC",
                    limit=page_size,
                    offset=page * page_size,
                )
                if not result.rows:
                    break
                process_page(result.rows)
                page += 1
            ```

            Overriding datasource:

            ```python
            # Query a different datasource
            result = ctx.query(
                "SELECT * FROM staging_orders",
                datasource_id="ds_staging",
            )
            ```

        Note:
            Results may be truncated if they exceed server limits. Check
            ``result.truncated`` to detect this condition.

        See Also:
            - `async_query`: Async version of this method
            - `dataing_sdk.types.QueryResult`: Return type
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
        """Async version of `query`.

        See `query` for full documentation.
        """
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

        Calculates the difference between current and previous values for a
        metric within the specified time window. This is useful for detecting
        changes and anomalies in data quality metrics.

        Supported Metrics:
            - ``row_count``: Total number of rows
            - ``null_rate``: Percentage of null values (per column or table)
            - ``distinct_count``: Number of unique values
            - ``freshness``: Time since last update
            - Custom metrics defined in your Dataing configuration

        Args:
            metric: The metric to compare. Must be a known metric type
                configured for the datasource.
            window: Time window for comparison using shorthand notation:

                - ``"24h"``: 24 hours
                - ``"7d"``: 7 days
                - ``"1w"``: 1 week
                - ``"30d"``: 30 days

            datasource_id: Override the default datasource for this comparison.

        Returns:
            A `dataing_sdk.types.DiffResult` containing current value,
            previous value, absolute delta, percentage change, and trend.

        Example:
            Basic comparison:

            ```python
            ctx = client.context("postgres://analytics.public.orders")

            # Check row count change
            diff = ctx.diff("row_count", "7d")
            print(f"Current: {diff.current_value:,}")
            print(f"Previous: {diff.previous_value:,}")
            print(f"Change: {diff.delta_percent:.1f}%")
            ```

            Detecting anomalies:

            ```python
            diff = ctx.diff("null_rate", "24h")

            if diff.trend == "increasing" and diff.delta_percent > 5:
                print("Warning: Null rate spiking!")
                print(f"Increased from {diff.previous_value}% to {diff.current_value}%")
            ```

            Checking freshness:

            ```python
            diff = ctx.diff("freshness", "1d")
            if diff.current_value > 3600:  # More than 1 hour stale
                print("Data is stale!")
            ```

        See Also:
            - `async_diff`: Async version of this method
            - `dataing_sdk.types.DiffResult`: Return type
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
        """Async version of `diff`.

        See `diff` for full documentation.
        """
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

        Uses an LLM to analyze the assets, lineage, and anomalies in the
        context and provide a natural language explanation with actionable
        insights. This is useful for understanding complex data relationships
        and getting quick answers about data quality.

        Focus Areas:
            - ``"anomalies"``: Focus on detected anomalies and their causes
            - ``"lineage"``: Explain upstream/downstream relationships
            - ``"data_quality"``: Overall data quality assessment
            - ``"schema"``: Schema structure and column analysis
            - ``None``: General overview of all aspects

        Args:
            focus: Optional focus area to emphasize in the explanation.
                If not provided, gives a general overview.

        Returns:
            An `dataing_sdk.types.ExplainResult` containing:

            - ``summary``: High-level natural language summary
            - ``insights``: List of specific findings and observations
            - ``recommendations``: Suggested actions to address issues
            - ``related_assets``: Other assets that may be relevant

        Example:
            General explanation:

            ```python
            ctx = client.context("postgres://analytics.public.orders")
            result = ctx.explain()

            print("Summary:")
            print(result.summary)

            print("\\nInsights:")
            for insight in result.insights:
                print(f"  - {insight}")

            print("\\nRecommendations:")
            for rec in result.recommendations:
                print(f"  - {rec}")
            ```

            Focused on anomalies:

            ```python
            result = ctx.explain(focus="anomalies")

            if "null spike" in result.summary.lower():
                print("Null spike detected!")
                print(result.summary)
            ```

            Understanding lineage:

            ```python
            result = ctx.explain(focus="lineage")
            print(f"Lineage analysis: {result.summary}")

            if result.related_assets:
                print("Related assets to investigate:")
                for asset in result.related_assets:
                    print(f"  - {asset}")
            ```

        Note:
            Explanations are generated using an LLM and may take a few seconds.
            Results are cached based on the bundle hash for efficiency.

        See Also:
            - `async_explain`: Async version of this method
            - `dataing_sdk.types.ExplainResult`: Return type
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
        """Async version of `explain`.

        See `explain` for full documentation.
        """
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
    """Extract asset references from a SQL query.

    Parses a SQL query using sqlglot to find all table references and converts
    them to `dataing_sdk.types.AssetRef` objects. This is useful for
    automatically building context from existing SQL queries.

    The function handles:

    - Qualified names: ``database.schema.table``
    - Partially qualified names: ``schema.table`` or just ``table``
    - Joins: All tables in JOIN clauses
    - Subqueries: Tables in nested queries
    - CTEs: Tables referenced in WITH clauses

    Args:
        sql: SQL query to parse. Can be any valid SQL statement.
        datasource_id: Datasource ID to assign to all extracted assets.
            If provided, all returned AssetRefs will have this ID set.
        default_platform: Platform identifier (e.g., ``"postgres"``,
            ``"snowflake"``) to use for URN construction. Required if
            ``datasource_id`` is not provided.
        dialect: SQL dialect for correct parsing. Supported values include
            ``"postgres"``, ``"snowflake"``, ``"bigquery"``, ``"mysql"``,
            ``"duckdb"``. If not specified, uses ANSI SQL parsing which
            may not handle all dialect-specific syntax.
        default_database: Default database/catalog name for unqualified
            table references. Applied when the SQL doesn't specify a database.
        default_schema: Default schema name for unqualified table references.
            Applied when the SQL doesn't specify a schema.

    Returns:
        A sorted list of `dataing_sdk.types.AssetRef` objects for
        each unique table referenced in the query.

    Raises:
        ValidationError: If neither ``datasource_id`` nor ``default_platform``
            is provided.
        ValidationError: If SQL parsing fails due to syntax errors.
        ImportError: If sqlglot is not installed. Install with:
            ``pip install 'dataing-sdk[sql]'``

    Example:
        Basic extraction:

        ```python
        from dataing_sdk.context import from_sql

        assets = from_sql(
            "SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id",
            default_platform="postgres",
            default_schema="public",
        )

        for asset in assets:
            print(f"{asset.platform}://{asset.name}")
        # postgres://public.customers
        # postgres://public.orders
        ```

        With datasource ID:

        ```python
        assets = from_sql(
            \"\"\"
            WITH recent_orders AS (
                SELECT * FROM analytics.orders WHERE created_at > NOW() - INTERVAL '7 days'
            )
            SELECT c.*, ro.total
            FROM analytics.customers c
            JOIN recent_orders ro ON c.id = ro.customer_id
            \"\"\",
            datasource_id="ds_analytics",
            dialect="postgres",
        )

        # Use with context
        ctx = client.context(assets=assets)
        ```

        Snowflake example:

        ```python
        assets = from_sql(
            "SELECT * FROM RAW_DB.STAGING.EVENTS",
            default_platform="snowflake",
            dialect="snowflake",
        )
        # Returns: [AssetRef(platform='snowflake', name='RAW_DB.STAGING.EVENTS')]
        ```

    Note:
        This function requires the ``sqlglot`` library. Install it with
        the ``[sql]`` extra: ``pip install 'dataing-sdk[sql]'``

    See Also:
        - `DataingClient.context`: Create context from extracted assets
        - `dataing_sdk.types.AssetRef`: The returned asset type
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
