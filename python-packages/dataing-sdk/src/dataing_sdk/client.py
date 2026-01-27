"""Dataing API client for Python.

This module provides the main entry point for interacting with the Dataing API.
The `DataingClient` class supports both synchronous and asynchronous
operations for creating context bundles, running investigations, and streaming
real-time events.

Environment Variables:
    DATAING_API_KEY: API key for authentication (required if not passed to client).
    DATAING_BASE_URL: Base URL for the API (default: http://localhost:8000).

Example:
    Basic synchronous usage:

    ```python
    from dataing_sdk import DataingClient
    from dataing_sdk.types import AssetRef

    # Create client (uses DATAING_API_KEY env var)
    client = DataingClient()

    # Attach a default datasource for the session
    client.attach("ds_prod", name="Production Analytics")

    # Create context for an asset
    ctx = client.context("postgres://analytics.public.orders")

    # Run an investigation
    run = client.run(
        assets=[AssetRef(platform="postgres", name="analytics.public.orders")],
        goal="Investigate the recent null spike in customer_id"
    )

    # Stream events in real-time
    for event in client.stream_run(run.run_id):
        print(f"[{event.event}] {event.data}")
    ```

    Async usage with context manager:

    ```python
    async with DataingClient() as client:
        ctx = await client.async_context("snowflake://db.schema.table")
        run = await client.async_run(
            assets=ctx.assets,
            goal="Check for schema drift"
        )
    ```

See Also:
    - `dataing_sdk.context.Context`: Rich context wrapper with query methods
    - `dataing_sdk.types.Run`: Investigation run status and metadata
    - `dataing_sdk.exceptions`: Exception types for error handling
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import httpx

from .exceptions import (
    AuthError,
    DataingError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)

if TYPE_CHECKING:
    from .context import Context
    from .types import AssetRef, ContextBundle, Run

# Environment variable for API key
ENV_API_KEY = "DATAING_API_KEY"
ENV_BASE_URL = "DATAING_BASE_URL"


class DataingClient:
    """Client for interacting with the Dataing API.

    The DataingClient is the primary interface for all Dataing operations. It
    supports both synchronous and asynchronous methods, uses connection pooling
    for efficiency, and can be used as a context manager for proper resource cleanup.

    The client provides methods for:

    - **Context Creation**: Build context bundles from asset references
    - **Investigation Runs**: Start and monitor automated data quality investigations
    - **Event Streaming**: Real-time SSE streaming of investigation progress
    - **Session Management**: Attach a default datasource for convenience

    Attributes:
        base_url: The base URL of the Dataing API server.
        api_key: The API key used for authentication.
        timeout: Request timeout in seconds.
        default_datasource_id: Currently attached datasource ID (via `attach`).
        default_datasource_name: Human-readable name of attached datasource.

    Example:
        Synchronous usage with explicit cleanup:

        ```python
        client = DataingClient(api_key="your-key")
        try:
            bundle = client.create_bundle(assets=[...])
            run = client.run(assets=[...], goal="Investigate nulls")
        finally:
            client.close()
        ```

        Using as a context manager (recommended):

        ```python
        with DataingClient() as client:
            ctx = client.context("postgres://db.schema.orders")
            result = ctx.query("SELECT COUNT(*) FROM orders")
        ```

        Async context manager:

        ```python
        async with DataingClient() as client:
            bundle = await client.async_create_bundle(assets=[...])
        ```

    Note:
        The client lazily initializes HTTP connections on first use. Use
        `close` or `aclose` to release resources, or use the
        context manager pattern for automatic cleanup.

    See Also:
        - `dataing_sdk.context.Context`: Rich wrapper for context bundles
        - `attach`: Set a default datasource for the session
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the Dataing client.

        Creates a new client instance configured for the specified API endpoint.
        The client does not establish connections until the first request is made.

        Args:
            base_url: Base URL of the Dataing API. Falls back to the
                ``DATAING_BASE_URL`` environment variable, then to
                ``http://localhost:8000`` if not set.
            api_key: API key for authentication. Falls back to the
                ``DATAING_API_KEY`` environment variable if not provided.
            timeout: Request timeout in seconds. Increase this for long-running
                operations like large context bundle creation.

        Raises:
            AuthError: Raised on first API call if no API key is available.

        Example:
            ```python
            # Use environment variables (recommended)
            client = DataingClient()

            # Explicit configuration
            client = DataingClient(
                base_url="https://api.dataing.io",
                api_key="dk_live_abc123",
                timeout=60.0,
            )
            ```

        Note:
            API keys can be created in the Dataing dashboard under
            Settings > API Keys.
        """
        self.base_url = (base_url or os.environ.get(ENV_BASE_URL, "http://localhost:8000")).rstrip(
            "/"
        )
        self.api_key = api_key or os.environ.get(ENV_API_KEY)
        self.timeout = timeout

        # Session default datasource (set via attach())
        self._default_datasource_id: str | None = None
        self._default_datasource_name: str | None = None

        # Lazy-initialized clients
        self._sync_client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _get_sync_client(self) -> httpx.Client:
        """Get or create sync HTTP client."""
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self.base_url,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
        return self._sync_client

    def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
        return self._async_client

    def _handle_response_error(self, response: httpx.Response) -> None:
        """Handle HTTP error responses by raising appropriate exceptions."""
        if response.status_code == 401:
            raise AuthError("Authentication failed: invalid or missing API key")
        elif response.status_code == 403:
            raise AuthError("Authorization failed: insufficient permissions")
        elif response.status_code == 404:
            raise NotFoundError(f"Resource not found: {response.url}")
        elif response.status_code == 422:
            try:
                detail = response.json().get("detail", "Validation error")
            except Exception:
                detail = response.text
            raise ValidationError(f"Validation error: {detail}")
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_seconds = float(retry_after) if retry_after else None
            raise RateLimitError("Rate limit exceeded", retry_after=retry_seconds)
        elif response.status_code >= 500:
            raise ServerError(f"Server error: {response.status_code}")
        elif response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise DataingError(f"Request failed: {detail}")

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a synchronous HTTP request."""
        client = self._get_sync_client()
        response = client.request(method, path, **kwargs)
        if not response.is_success:
            self._handle_response_error(response)
        return response

    async def _async_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an asynchronous HTTP request."""
        client = self._get_async_client()
        response = await client.request(method, path, **kwargs)
        if not response.is_success:
            self._handle_response_error(response)
        return response

    def close(self) -> None:
        """Close the synchronous HTTP client."""
        if self._sync_client is not None:
            self._sync_client.close()
            self._sync_client = None

    async def aclose(self) -> None:
        """Close the asynchronous HTTP client."""
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    def __enter__(self) -> DataingClient:
        """Enter context manager for sync usage."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager for sync usage."""
        self.close()

    async def __aenter__(self) -> DataingClient:
        """Enter context manager for async usage."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit context manager for async usage."""
        await self.aclose()

    # --- Session and Attachment methods ---

    @property
    def default_datasource_id(self) -> str | None:
        """Get the session default datasource ID."""
        return self._default_datasource_id

    @property
    def default_datasource_name(self) -> str | None:
        """Get the session default datasource name."""
        return self._default_datasource_name

    def attach(self, datasource_id: str, name: str | None = None) -> None:
        """Set the session default datasource.

        Attaching a datasource sets it as the default for all subsequent
        operations that require a datasource. This is particularly useful in
        notebook environments where you want to work with a single data source
        across multiple operations.

        The attached datasource is used when:

        - Creating context bundles without explicit ``datasource_id``
        - Running queries through `Context.query`
        - Resolving asset URNs that don't specify a datasource

        Args:
            datasource_id: The datasource ID to use as default. This should
                match a datasource configured in your Dataing account.
            name: Optional human-readable name for display in notebooks
                and logs. If not provided, the ``datasource_id`` is used.

        Example:
            ```python
            # Attach for the session
            client.attach("ds_prod", name="Production Analytics")
            print(client)  # DataingClient(base_url='...', datasource='Production Analytics')

            # Subsequent operations use ds_prod automatically
            ctx = client.context("postgres://db.public.orders")
            result = ctx.query("SELECT * FROM orders LIMIT 10")

            # Clear attachment when done
            client.detach()
            ```

        See Also:
            - `detach`: Clear the attached datasource
            - `default_datasource_id`: Access the current attachment
        """
        self._default_datasource_id = datasource_id
        self._default_datasource_name = name

    def detach(self) -> None:
        """Clear the session default datasource.

        After calling this method, operations that require a datasource will
        need to have it explicitly specified via parameter or asset URN.

        Example:
            ```python
            client.attach("ds_prod")
            # ... work with ds_prod ...
            client.detach()
            print(client.default_datasource_id)  # None
            ```

        See Also:
            - `attach`: Set the default datasource
        """
        self._default_datasource_id = None
        self._default_datasource_name = None

    def __repr__(self) -> str:
        """Return string representation showing connection and datasource."""
        parts = [f"DataingClient(base_url='{self.base_url}'"]
        if self._default_datasource_id:
            ds_info = self._default_datasource_name or self._default_datasource_id
            parts.append(f", datasource='{ds_info}'")
        parts.append(")")
        return "".join(parts)

    # --- Bundle and Context methods ---

    def create_bundle(
        self,
        assets: list[AssetRef],
        window: str | None = None,
        include_lineage: bool = True,
        include_operational: bool = True,
        include_anomalies: bool = True,
    ) -> ContextBundle:
        """Create a context bundle for the given assets.

        A context bundle is a snapshot of all relevant information about a set
        of data assets, including their schemas, statistics, lineage relationships,
        and any detected anomalies. Bundles are cached server-side based on their
        content hash (``bundle_hash``), so repeated requests with the same assets
        return quickly.

        Args:
            assets: List of `dataing_sdk.types.AssetRef` objects
                identifying the data assets to include.
            window: Time window for historical context. Supports formats like
                ``"7d"`` (7 days), ``"24h"`` (24 hours), ``"1w"`` (1 week).
                If not specified, uses the server default.
            include_lineage: Whether to fetch and include the lineage graph
                showing upstream and downstream dependencies.
            include_operational: Whether to include operational metadata like
                last update times, job run history, and freshness metrics.
            include_anomalies: Whether to include any detected anomalies
                for the assets from the configured anomaly detection system.

        Returns:
            A `dataing_sdk.types.ContextBundle` containing resolved
            assets, schemas, and requested context data.

        Example:
            ```python
            from dataing_sdk.types import AssetRef

            bundle = client.create_bundle(
                assets=[
                    AssetRef(platform="postgres", name="analytics.public.orders"),
                    AssetRef(platform="postgres", name="analytics.public.customers"),
                ],
                window="7d",
                include_lineage=True,
            )

            print(f"Bundle ID: {bundle.bundle_id}")
            print(f"Hash (cache key): {bundle.bundle_hash}")
            for asset in bundle.resolved_assets:
                print(f"  - {asset.dataset_id}")
            ```

        Note:
            For most use cases, prefer `context` which wraps the bundle
            in a `dataing_sdk.context.Context` object with convenient
            query and analysis methods.

        See Also:
            - `context`: Higher-level context creation with URN support
            - `async_create_bundle`: Async version of this method
        """
        from .types import ContextBundle

        payload = {
            "assets": [
                {
                    "platform": a.platform,
                    "name": a.name,
                    "datasource_id": a.datasource_id,
                }
                for a in assets
            ],
            "window": window,
            "include_lineage": include_lineage,
            "include_operational": include_operational,
            "include_anomalies": include_anomalies,
        }
        response = self._request("POST", "/api/v1/context/bundles", json=payload)
        data = response.json()
        return ContextBundle.model_validate(data)

    async def async_create_bundle(
        self,
        assets: list[AssetRef],
        window: str | None = None,
        include_lineage: bool = True,
        include_operational: bool = True,
        include_anomalies: bool = True,
    ) -> ContextBundle:
        """Async version of `create_bundle`.

        See `create_bundle` for full documentation.
        """
        from .types import ContextBundle

        payload = {
            "assets": [
                {
                    "platform": a.platform,
                    "name": a.name,
                    "datasource_id": a.datasource_id,
                }
                for a in assets
            ],
            "window": window,
            "include_lineage": include_lineage,
            "include_operational": include_operational,
            "include_anomalies": include_anomalies,
        }
        response = await self._async_request("POST", "/api/v1/context/bundles", json=payload)
        data = response.json()
        return ContextBundle.model_validate(data)

    def context(
        self,
        *urns: str,
        assets: list[AssetRef] | None = None,
        window: str | None = None,
    ) -> Context:
        """Create a Context for the given assets.

        This is the primary method for building investigation context. It accepts
        URN strings for convenience, creates a context bundle server-side, and
        returns a `dataing_sdk.context.Context` object with methods for
        querying, diffing, and explaining the data.

        The Context object provides:

        - `dataing_sdk.context.Context.query`: Execute SQL queries
        - `dataing_sdk.context.Context.diff`: Compare metrics over time
        - `dataing_sdk.context.Context.explain`: Get AI-powered explanations

        Args:
            *urns: URN strings identifying assets. Format varies by platform:

                - PostgreSQL: ``postgres://database.schema.table``
                - Snowflake: ``snowflake://database.schema.table``
                - BigQuery: ``bigquery://project.dataset.table``
                - DuckDB: ``duckdb://database.schema.table``

            assets: List of `dataing_sdk.types.AssetRef` objects.
                Can be combined with URN arguments.
            window: Time window for historical context (e.g., ``"7d"``, ``"24h"``).

        Returns:
            A `dataing_sdk.context.Context` object wrapping the bundle
            with additional query and analysis methods.

        Raises:
            ValidationError: If no assets are provided (neither URNs nor assets list).
            AmbiguousAssetError: If a URN matches multiple datasources and no
                ``datasource_id`` is specified.

        Example:
            Single asset with URN:

            ```python
            ctx = client.context("postgres://analytics.public.orders")
            print(ctx.resolved_assets)
            ```

            Multiple assets:

            ```python
            ctx = client.context(
                "postgres://analytics.public.orders",
                "postgres://analytics.public.customers",
                window="7d",
            )
            for asset in ctx.resolved_assets:
                print(f"- {asset.dataset_id}")
            ```

            Using AssetRef objects:

            ```python
            from dataing_sdk.types import AssetRef

            ctx = client.context(
                assets=[
                    AssetRef(platform="postgres", name="db.schema.orders"),
                    AssetRef(platform="postgres", name="db.schema.customers"),
                ]
            )
            ```

        See Also:
            - `dataing_sdk.context.Context`: The returned context object
            - `dataing_sdk.context.from_sql`: Extract assets from SQL queries
            - `async_context`: Async version of this method
        """
        from .context import Context
        from .types import AssetRef as AssetRefType

        # Build asset list from URNs and/or assets parameter
        asset_list: list[AssetRefType] = []
        for urn in urns:
            asset_list.append(AssetRefType.from_urn(urn))
        if assets:
            asset_list.extend(assets)

        if not asset_list:
            raise ValidationError("At least one asset URN or AssetRef is required")

        bundle = self.create_bundle(asset_list, window=window)
        return Context(bundle, self)

    async def async_context(
        self,
        *urns: str,
        assets: list[AssetRef] | None = None,
        window: str | None = None,
    ) -> Context:
        """Async version of `context`.

        See `context` for full documentation.
        """
        from .context import Context
        from .types import AssetRef as AssetRefType

        asset_list: list[AssetRefType] = []
        for urn in urns:
            asset_list.append(AssetRefType.from_urn(urn))
        if assets:
            asset_list.extend(assets)

        if not asset_list:
            raise ValidationError("At least one asset URN or AssetRef is required")

        bundle = await self.async_create_bundle(asset_list, window=window)
        return Context(bundle, self)

    # --- Run methods ---

    def run(
        self,
        assets: list[AssetRef],
        goal: str,
        bundle_id: str | None = None,
    ) -> Run:
        """Create and start an investigation run.

        .. deprecated::
            Use `start_investigation` instead for better investigation quality.
            This method now internally calls `start_investigation` with the
            ``user_query`` anomaly type.

        This is the legacy method for launching investigations. It has been
        updated to use the unified investigations endpoint (same as the GUI)
        for consistent results.

        Args:
            assets: List of `dataing_sdk.types.AssetRef` objects
                identifying the data assets to investigate.
            goal: Natural language description of what to investigate.
                Be specific about the issue or question, e.g.,
                ``"Why are there null values spiking in customer_id?"``
            bundle_id: Optional ID of an existing context bundle to reuse.
                (Note: Currently ignored - provided for API compatibility)

        Returns:
            A `dataing_sdk.types.Run` object with the ``run_id``,
            initial ``status``, and associated ``bundle_id``.

        Raises:
            ValidationError: If ``goal`` is empty or ``assets`` is empty.
            AuthError: If authentication fails.
            ServerError: If the server encounters an error starting the run.

        Example:
            Basic investigation:

            ```python
            from dataing_sdk.types import AssetRef

            run = client.run(
                assets=[AssetRef(platform="postgres", name="db.public.orders")],
                goal="Investigate the 40% drop in order volume yesterday"
            )
            print(f"Started run: {run.run_id}")
            ```

        See Also:
            - `start_investigation`: Preferred method with structured anomaly data
            - `get_run`: Check run status
            - `wait_for_run`: Block until run completes
            - `stream_run`: Stream real-time events
        """
        import warnings
        from datetime import datetime

        from .types import Run, RunStatus

        warnings.warn(
            "run() is deprecated. Use start_investigation() for better results.",
            DeprecationWarning,
            stacklevel=2,
        )

        if not assets:
            raise ValidationError("At least one asset is required")

        # Use first asset's name and datasource_id
        first_asset = assets[0]
        dataset = first_asset.name
        datasource_id = first_asset.datasource_id

        # Call start_investigation with user_query anomaly type
        investigation = self.start_investigation(
            dataset=dataset,
            anomaly_type="user_query",
            goal=goal,
            datasource_id=datasource_id,
        )

        # Return a Run object for backward compatibility
        return Run(
            run_id=investigation.investigation_id,
            bundle_id=bundle_id or investigation.investigation_id,
            bundle_hash="",
            status=RunStatus.RUNNING,
            created_at=datetime.now(),
        )

    async def async_run(
        self,
        assets: list[AssetRef],
        goal: str,
        bundle_id: str | None = None,
    ) -> Run:
        """Async version of `run`.

        .. deprecated::
            Use `async_start_investigation` instead for better investigation quality.

        See `run` for full documentation.
        """
        import warnings
        from datetime import datetime

        from .types import Run, RunStatus

        warnings.warn(
            "async_run() is deprecated. Use async_start_investigation() for better results.",
            DeprecationWarning,
            stacklevel=2,
        )

        if not assets:
            raise ValidationError("At least one asset is required")

        # Use first asset's name and datasource_id
        first_asset = assets[0]
        dataset = first_asset.name
        datasource_id = first_asset.datasource_id

        # Call async_start_investigation with user_query anomaly type
        investigation = await self.async_start_investigation(
            dataset=dataset,
            anomaly_type="user_query",
            goal=goal,
            datasource_id=datasource_id,
        )

        # Return a Run object for backward compatibility
        return Run(
            run_id=investigation.investigation_id,
            bundle_id=bundle_id or investigation.investigation_id,
            bundle_hash="",
            status=RunStatus.RUNNING,
            created_at=datetime.now(),
        )

    # --- Investigation methods (unified with GUI) ---

    def start_investigation(
        self,
        dataset: str,
        anomaly_type: str,
        goal: str,
        column: str | None = None,
        expected_value: float = 0.0,
        actual_value: float = 0.0,
        deviation_pct: float | None = None,
        severity: str = "medium",
        datasource_id: str | None = None,
        anomaly_date: str | None = None,
    ) -> Any:
        """Start an investigation using the same endpoint as the GUI.

        This method provides a unified experience between CLI and GUI by calling
        the same ``/api/v1/investigations`` endpoint with structured anomaly data.
        This ensures consistent investigation quality across all interfaces.

        Args:
            dataset: The dataset to investigate in ``schema.table`` format.
            anomaly_type: Type of anomaly being investigated. Common values:
                - ``null_rate``: Null values in a column
                - ``row_count``: Unexpected row count change
                - ``freshness``: Data not updated as expected
                - ``duplicate_rate``: Duplicate records detected
                - ``schema_drift``: Schema changes detected
                - ``custom``: Custom/other anomaly type
            goal: Natural language description of what to investigate.
            column: Optional column name if the anomaly is column-specific.
            expected_value: Expected metric value (default 0.0).
            actual_value: Actual observed metric value (default 0.0).
            deviation_pct: Percentage deviation. If not provided, calculated
                from expected and actual values.
            severity: Alert severity level (``low``, ``medium``, ``high``, ``critical``).
            datasource_id: Optional datasource UUID. If not provided, uses the
                attached datasource or tenant default.
            anomaly_date: Date of the anomaly in ``YYYY-MM-DD`` format.
                Defaults to today.

        Returns:
            An `Investigation` object with ``investigation_id``, ``main_branch_id``,
            and initial ``status``.

        Raises:
            ValidationError: If required fields are missing or invalid.
            AuthError: If authentication fails.
            ServerError: If the server encounters an error.

        Example:
            Full structured input (matches GUI experience):

            ```python
            inv = client.start_investigation(
                dataset="main.orders",
                anomaly_type="null_rate",
                column="user_id",
                expected_value=0.01,
                actual_value=0.15,
                goal="Investigate why user_id has null values",
            )
            print(f"Started: {inv.investigation_id}")
            ```

            Minimal input with sensible defaults:

            ```python
            inv = client.start_investigation(
                dataset="main.orders",
                anomaly_type="null_rate",
                goal="Investigate null spike",
            )
            ```

        See Also:
            - `run`: Legacy method using runs endpoint
            - `stream_run`: Stream real-time events
            - `async_start_investigation`: Async version
        """
        from datetime import date

        from .types import Investigation

        # Calculate deviation if not provided
        if deviation_pct is None:
            if expected_value != 0:
                deviation_pct = ((actual_value - expected_value) / expected_value) * 100
            else:
                deviation_pct = 0.0

        # Use today's date if not provided
        if anomaly_date is None:
            anomaly_date = date.today().isoformat()

        # Resolve datasource_id
        ds_id = datasource_id or self._default_datasource_id

        # Build metric_spec based on whether column is specified
        if column:
            metric_spec = {
                "metric_type": "column",
                "expression": column,
                "display_name": f"{anomaly_type} on {column}",
                "columns_referenced": [column],
            }
        else:
            metric_spec = {
                "metric_type": "description",
                "expression": goal,
                "display_name": anomaly_type,
                "columns_referenced": [],
            }

        # Build alert payload matching AnomalyAlert structure
        alert_payload = {
            "dataset_ids": [dataset],
            "metric_spec": metric_spec,
            "anomaly_type": anomaly_type,
            "expected_value": expected_value,
            "actual_value": actual_value,
            "deviation_pct": deviation_pct,
            "anomaly_date": anomaly_date,
            "severity": severity,
        }

        # Build request payload
        payload: dict[str, Any] = {"alert": alert_payload}
        if ds_id:
            payload["datasource_id"] = ds_id

        response = self._request("POST", "/api/v1/investigations", json=payload)
        data = response.json()

        return Investigation(
            investigation_id=str(data["investigation_id"]),
            main_branch_id=str(data["main_branch_id"]),
            status=data.get("status", "queued"),
        )

    async def async_start_investigation(
        self,
        dataset: str,
        anomaly_type: str,
        goal: str,
        column: str | None = None,
        expected_value: float = 0.0,
        actual_value: float = 0.0,
        deviation_pct: float | None = None,
        severity: str = "medium",
        datasource_id: str | None = None,
        anomaly_date: str | None = None,
    ) -> Any:
        """Async version of `start_investigation`.

        See `start_investigation` for full documentation.
        """
        from datetime import date

        from .types import Investigation

        # Calculate deviation if not provided
        if deviation_pct is None:
            if expected_value != 0:
                deviation_pct = ((actual_value - expected_value) / expected_value) * 100
            else:
                deviation_pct = 0.0

        # Use today's date if not provided
        if anomaly_date is None:
            anomaly_date = date.today().isoformat()

        # Resolve datasource_id
        ds_id = datasource_id or self._default_datasource_id

        # Build metric_spec based on whether column is specified
        if column:
            metric_spec = {
                "metric_type": "column",
                "expression": column,
                "display_name": f"{anomaly_type} on {column}",
                "columns_referenced": [column],
            }
        else:
            metric_spec = {
                "metric_type": "description",
                "expression": goal,
                "display_name": anomaly_type,
                "columns_referenced": [],
            }

        # Build alert payload matching AnomalyAlert structure
        alert_payload = {
            "dataset_ids": [dataset],
            "metric_spec": metric_spec,
            "anomaly_type": anomaly_type,
            "expected_value": expected_value,
            "actual_value": actual_value,
            "deviation_pct": deviation_pct,
            "anomaly_date": anomaly_date,
            "severity": severity,
        }

        # Build request payload
        payload: dict[str, Any] = {"alert": alert_payload}
        if ds_id:
            payload["datasource_id"] = ds_id

        response = await self._async_request("POST", "/api/v1/investigations", json=payload)
        data = response.json()

        return Investigation(
            investigation_id=str(data["investigation_id"]),
            main_branch_id=str(data["main_branch_id"]),
            status=data.get("status", "queued"),
        )

    def get_investigation(self, investigation_id: str) -> Any:
        """Get the current state of an investigation.

        Fetches the full investigation state including evidence collected,
        synthesis results, and branch status.

        Args:
            investigation_id: The unique identifier of the investigation.

        Returns:
            An `InvestigationState` object containing the full investigation
            state including main_branch with evidence and synthesis.

        Raises:
            NotFoundError: If the investigation ID does not exist.
            AuthError: If not authorized to access this investigation.

        Example:
            ```python
            inv = client.start_investigation(
                dataset="main.orders",
                anomaly_type="null_rate",
                goal="Investigate nulls",
            )

            # Wait for completion, then get full state
            # ...

            state = client.get_investigation(inv.investigation_id)
            if state.synthesis:
                print(f"Root cause: {state.synthesis.get('root_cause')}")
            for ev in state.evidence:
                print(f"Evidence: {ev.get('kind')}")
            ```

        See Also:
            - `start_investigation`: Start a new investigation
            - `stream_run`: Stream real-time events
        """
        from .types import BranchState, InvestigationState

        response = self._request("GET", f"/api/v1/investigations/{investigation_id}")
        data = response.json()

        # Parse main branch
        main_branch_data = data.get("main_branch", {})
        main_branch = BranchState(
            branch_id=str(main_branch_data.get("branch_id", investigation_id)),
            status=main_branch_data.get("status", data.get("status", "unknown")),
            current_step=main_branch_data.get("current_step", "unknown"),
            synthesis=main_branch_data.get("synthesis"),
            evidence=main_branch_data.get("evidence", []),
        )

        # Parse user branch if present
        user_branch = None
        user_branch_data = data.get("user_branch")
        if user_branch_data:
            user_branch = BranchState(
                branch_id=str(user_branch_data.get("branch_id", "")),
                status=user_branch_data.get("status", "unknown"),
                current_step=user_branch_data.get("current_step", "unknown"),
                synthesis=user_branch_data.get("synthesis"),
                evidence=user_branch_data.get("evidence", []),
            )

        return InvestigationState(
            investigation_id=str(data["investigation_id"]),
            status=data.get("status", "unknown"),
            main_branch=main_branch,
            user_branch=user_branch,
            root_hash=data.get("root_hash"),
        )

    def send_message(self, investigation_id: str, message: str) -> Any:
        """Send a user message to an investigation.

        Sends a follow-up message to an ongoing investigation, allowing users
        to provide additional context, ask questions, or redirect the
        investigation focus.

        Args:
            investigation_id: The unique identifier of the investigation.
            message: The user message text to send.

        Returns:
            A `SendMessageResponse` object with status and investigation_id.

        Raises:
            NotFoundError: If the investigation ID does not exist.
            AuthError: If not authorized to access this investigation.
            DataingError: If the message could not be sent.

        Example:
            ```python
            inv = client.start_investigation(
                dataset="main.orders",
                anomaly_type="null_rate",
                goal="Investigate nulls",
            )

            # Later, send a follow-up message
            response = client.send_message(
                inv.investigation_id,
                "Can you also check the upstream data source?"
            )
            print(f"Message status: {response.status}")
            ```

        See Also:
            - `start_investigation`: Start a new investigation
            - `get_investigation`: Get current investigation state
            - `stream_run`: Stream real-time events
        """
        from .types import SendMessageResponse

        response = self._request(
            "POST",
            f"/api/v1/investigations/{investigation_id}/messages",
            json={"message": message},
        )
        data = response.json()

        return SendMessageResponse(
            status=data.get("status", "unknown"),
            investigation_id=str(data.get("investigation_id", investigation_id)),
        )

    async def async_send_message(self, investigation_id: str, message: str) -> Any:
        """Async version of `send_message`.

        See `send_message` for full documentation.
        """
        from .types import SendMessageResponse

        response = await self._async_request(
            "POST",
            f"/api/v1/investigations/{investigation_id}/messages",
            json={"message": message},
        )
        data = response.json()

        return SendMessageResponse(
            status=data.get("status", "unknown"),
            investigation_id=str(data.get("investigation_id", investigation_id)),
        )

    def verify_investigation(self, investigation_id: str) -> Any:
        """Verify the evidence hash chain of an investigation.

        Checks that the hash chain is intact and untampered by calling the
        server-side verification endpoint.

        Args:
            investigation_id: The unique identifier of the investigation.

        Returns:
            A `ChainVerificationResult` with verification details.

        Raises:
            NotFoundError: If the investigation ID does not exist.
            AuthError: If not authorized to access this investigation.

        Example:
            ```python
            result = client.verify_investigation("inv-abc123")
            if result.is_valid:
                print(f"Valid chain: {result.evidence_count} items")
            else:
                print(f"Broken at seq {result.first_broken_seq}: {result.error}")
            ```
        """
        from .types import ChainVerificationResult

        response = self._request("GET", f"/api/v1/investigations/{investigation_id}/verify")
        return ChainVerificationResult.model_validate(response.json())

    async def async_verify_investigation(self, investigation_id: str) -> Any:
        """Async version of `verify_investigation`.

        See `verify_investigation` for full documentation.
        """
        from .types import ChainVerificationResult

        response = await self._async_request(
            "GET", f"/api/v1/investigations/{investigation_id}/verify"
        )
        return ChainVerificationResult.model_validate(response.json())

    async def async_get_investigation(self, investigation_id: str) -> Any:
        """Async version of `get_investigation`.

        See `get_investigation` for full documentation.
        """
        from .types import BranchState, InvestigationState

        response = await self._async_request("GET", f"/api/v1/investigations/{investigation_id}")
        data = response.json()

        # Parse main branch
        main_branch_data = data.get("main_branch", {})
        main_branch = BranchState(
            branch_id=str(main_branch_data.get("branch_id", investigation_id)),
            status=main_branch_data.get("status", data.get("status", "unknown")),
            current_step=main_branch_data.get("current_step", "unknown"),
            synthesis=main_branch_data.get("synthesis"),
            evidence=main_branch_data.get("evidence", []),
        )

        # Parse user branch if present
        user_branch = None
        user_branch_data = data.get("user_branch")
        if user_branch_data:
            user_branch = BranchState(
                branch_id=str(user_branch_data.get("branch_id", "")),
                status=user_branch_data.get("status", "unknown"),
                current_step=user_branch_data.get("current_step", "unknown"),
                synthesis=user_branch_data.get("synthesis"),
                evidence=user_branch_data.get("evidence", []),
            )

        return InvestigationState(
            investigation_id=str(data["investigation_id"]),
            status=data.get("status", "unknown"),
            main_branch=main_branch,
            user_branch=user_branch,
            root_hash=data.get("root_hash"),
        )

    # --- Run status methods ---

    def get_run(self, run_id: str) -> Run:
        """Get the current status and metadata of a run.

        Use this method to check whether a run has completed, is still running,
        or has failed. For waiting until completion, consider `wait_for_run`
        or `stream_run` instead.

        Args:
            run_id: The unique identifier of the run to check.

        Returns:
            A `dataing_sdk.types.Run` object with the current status
            and metadata.

        Raises:
            NotFoundError: If the run ID does not exist.
            AuthError: If not authorized to access this run.

        Example:
            ```python
            run = client.run(assets=[...], goal="...")
            # Later...
            status = client.get_run(run.run_id)
            if status.status == RunStatus.COMPLETED:
                print("Investigation complete!")
            elif status.status == RunStatus.FAILED:
                print("Investigation failed")
            ```

        See Also:
            - `wait_for_run`: Block until run completes
            - `stream_run`: Stream events in real-time
        """
        from .types import Run, RunStatus

        response = self._request("GET", f"/api/v1/runs/{run_id}")
        data = response.json()

        return Run(
            run_id=data["run_id"],
            bundle_id=data["bundle_id"],
            bundle_hash=data["bundle_hash"],
            status=RunStatus(data["status"]),
            created_at=data["created_at"],
        )

    async def async_get_run(self, run_id: str) -> Run:
        """Async version of `get_run`.

        See `get_run` for full documentation.
        """
        from .types import Run, RunStatus

        response = await self._async_request("GET", f"/api/v1/runs/{run_id}")
        data = response.json()

        return Run(
            run_id=data["run_id"],
            bundle_id=data["bundle_id"],
            bundle_hash=data["bundle_hash"],
            status=RunStatus(data["status"]),
            created_at=data["created_at"],
        )

    def wait_for_run(
        self,
        run_id: str,
        poll_interval: float = 1.0,
        timeout: float | None = 300.0,
        on_progress: Any | None = None,
    ) -> Run:
        """Wait for a run to complete by polling.

        Blocks the current thread until the run reaches a terminal state
        (completed, failed, or cancelled). For real-time event streaming,
        use `stream_run` instead.

        Args:
            run_id: The unique identifier of the run to wait for.
            poll_interval: Seconds between status checks. Lower values
                provide faster detection but more API calls.
            timeout: Maximum seconds to wait before raising TimeoutError.
                Set to ``None`` for no timeout (not recommended).
            on_progress: Optional callback function that receives the
                `dataing_sdk.types.Run` object on each poll.
                Useful for progress updates in CLI applications.

        Returns:
            The final `dataing_sdk.types.Run` object with terminal status.

        Raises:
            TimeoutError: If the run does not complete within the timeout.
            NotFoundError: If the run ID does not exist.

        Example:
            Basic waiting:

            ```python
            run = client.run(assets=[...], goal="...")
            final = client.wait_for_run(run.run_id, timeout=120)
            print(f"Final status: {final.status}")
            ```

            With progress callback:

            ```python
            def show_progress(run):
                print(f"Status: {run.status.value}...")

            final = client.wait_for_run(
                run.run_id,
                poll_interval=2.0,
                on_progress=show_progress,
            )
            ```

        Note:
            For long-running investigations, consider using `stream_run`
            which provides real-time event streaming without polling overhead.

        See Also:
            - `stream_run`: Real-time SSE event streaming
            - `get_run`: Single status check
        """
        import time

        start = time.time()
        terminal_statuses = {"completed", "failed", "cancelled"}

        while True:
            run = self.get_run(run_id)

            if on_progress:
                on_progress(run)

            if run.status.value in terminal_statuses:
                return run

            if timeout and (time.time() - start) > timeout:
                raise TimeoutError(f"Run {run_id} did not complete within {timeout}s")

            time.sleep(poll_interval)

    def stream_run(
        self,
        run_id: str,
        last_seq: int | None = None,
        timeout: float = 300.0,
    ) -> Any:
        """Stream SSE events from a run in real-time.

        Opens a Server-Sent Events (SSE) connection to receive investigation
        events as they occur. This is the recommended approach for monitoring
        long-running investigations, as it provides immediate feedback without
        polling overhead.

        Event Types:
            - ``run_started``: Investigation has begun
            - ``context_gathered``: Context bundle created
            - ``hypothesis_generated``: New hypothesis proposed
            - ``hypothesis_testing``: Testing a hypothesis with SQL
            - ``hypothesis_result``: Test result received
            - ``synthesis_started``: Beginning to synthesize findings
            - ``run_completed``: Investigation finished successfully
            - ``run_failed``: Investigation encountered an error

        Args:
            run_id: The unique identifier of the run to stream.
            last_seq: Sequence number to resume from after a disconnection.
                The server keeps events for a limited replay window (typically
                30 seconds). If the window has expired, raises
                `dataing_sdk.exceptions.ReplayWindowExpiredError`.
            timeout: Connection timeout in seconds. The SSE connection may
                remain open for the entire investigation duration.

        Yields:
            `dataing_sdk.types.RunEvent` objects as they arrive from
            the server.

        Raises:
            NotFoundError: If the run ID does not exist.
            ReplayWindowExpiredError: If ``last_seq`` is too old for replay.
            StreamError: If the SSE connection encounters an error.

        Example:
            Basic streaming:

            ```python
            run = client.run(assets=[...], goal="...")

            for event in client.stream_run(run.run_id):
                print(f"[{event.event}] {event.data}")
                if event.event == "run_completed":
                    print("Investigation complete!")
                    break
                elif event.event == "run_failed":
                    print(f"Failed: {event.data.get('error')}")
                    break
            ```

            With reconnection handling:

            ```python
            last_seq = None
            while True:
                try:
                    for event in client.stream_run(run.run_id, last_seq=last_seq):
                        last_seq = event.seq
                        process_event(event)
                        if event.event in ("run_completed", "run_failed"):
                            break
                    break  # Normal completion
                except StreamError:
                    print("Connection lost, reconnecting...")
                    continue
            ```

        Note:
            In Jupyter notebooks, consider using the ``dataing-notebook``
            extension which provides a rich timeline widget for streaming events.

        See Also:
            - `dataing_sdk.types.RunEvent`: Event data structure
            - `wait_for_run`: Simple polling alternative
        """
        from .types import RunEvent

        url = f"{self.base_url}/api/v1/investigations/{run_id}/events"
        params = {}
        if last_seq is not None:
            params["seq"] = str(last_seq)

        headers = self._get_headers()
        headers["Accept"] = "text/event-stream"

        # Use httpx streaming for SSE
        with httpx.stream(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        ) as response:
            if not response.is_success:
                self._handle_response_error(response)

            event_type = None
            event_data = ""

            for line in response.iter_lines():
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    event_data = line[5:].strip()
                elif line == "" and event_type and event_data:
                    # Complete event received
                    import json

                    try:
                        data = json.loads(event_data)
                        yield RunEvent(
                            seq=data.get("seq", 0),
                            event=event_type,
                            run_id=data.get("run_id", run_id),
                            data=data.get("data", {}),
                            timestamp=data.get("timestamp"),
                        )
                    except json.JSONDecodeError:
                        pass

                    # Check for terminal events before resetting
                    is_terminal = event_type in ("run_completed", "run_failed")

                    # Reset for next event
                    event_type = None
                    event_data = ""

                    if is_terminal:
                        break

    # --- Health check ---

    def health(self) -> dict[str, Any]:
        """Check API health and connectivity.

        Verifies that the Dataing API is reachable and responding. This is
        useful for connection testing before starting longer operations.

        Returns:
            A dictionary containing health status information, typically
            including ``status`` (``"ok"`` or ``"degraded"``), ``version``,
            and component health details.

        Raises:
            AuthError: If the API key is invalid (health endpoint may require auth).
            ServerError: If the server is unreachable or unhealthy.

        Example:
            ```python
            try:
                health = client.health()
                print(f"API Status: {health['status']}")
                print(f"Version: {health.get('version', 'unknown')}")
            except ServerError:
                print("API is unreachable")
            ```

        See Also:
            - `async_health`: Async version of this method
        """
        response = self._request("GET", "/health")
        return response.json()

    async def async_health(self) -> dict[str, Any]:
        """Async version of `health`.

        See `health` for full documentation.
        """
        response = await self._async_request("GET", "/health")
        return response.json()

    # --- Datasource management ---

    def list_datasources(self) -> list:
        """List all datasources for the current tenant.

        Retrieves all configured datasources accessible with the current API key.

        Returns:
            A list of Datasource objects.

        Raises:
            AuthError: If the API key is invalid.
            ServerError: If the server is unreachable.

        Example:
            ```python
            datasources = client.list_datasources()
            for ds in datasources:
                print(f"{ds.name} ({ds.source_type}): {ds.status}")
            ```

        See Also:
            - `test_datasource`: Test connectivity to a datasource
            - `get_schema`: Get schema information for a datasource
        """
        from .types import Datasource

        response = self._request("GET", "/api/v1/datasources")
        data = response.json()
        return [Datasource.model_validate(ds) for ds in data.get("items", [])]

    async def async_list_datasources(self) -> list:
        """Async version of `list_datasources`.

        See `list_datasources` for full documentation.
        """
        from .types import Datasource

        response = await self._async_request("GET", "/api/v1/datasources")
        data = response.json()
        return [Datasource.model_validate(ds) for ds in data.get("items", [])]

    def test_datasource(self, datasource_id: str):
        """Test connectivity to a datasource.

        Attempts to connect to the specified datasource and run a simple
        query to verify connectivity.

        Args:
            datasource_id: The ID of the datasource to test.

        Returns:
            A ConnectionTestResult indicating success or failure.

        Raises:
            NotFoundError: If the datasource doesn't exist.
            AuthError: If not authorized to access the datasource.

        Example:
            ```python
            result = client.test_datasource("ds-prod-123")
            if result.success:
                print(f"Connected in {result.latency_ms}ms")
            else:
                print(f"Connection failed: {result.error}")
            ```
        """
        from .types import ConnectionTestResult

        response = self._request("POST", f"/api/v1/datasources/{datasource_id}/test")
        return ConnectionTestResult.model_validate(response.json())

    async def async_test_datasource(self, datasource_id: str):
        """Async version of `test_datasource`.

        See `test_datasource` for full documentation.
        """
        from .types import ConnectionTestResult

        response = await self._async_request("POST", f"/api/v1/datasources/{datasource_id}/test")
        return ConnectionTestResult.model_validate(response.json())

    def get_schema(self, datasource_id: str):
        r"""Get schema information for a datasource.

        Retrieves the database schema including all tables and their columns
        for the specified datasource.

        Args:
            datasource_id: The ID of the datasource.

        Returns:
            A DatasourceSchema containing table and column definitions.

        Raises:
            NotFoundError: If the datasource doesn't exist.
            AuthError: If not authorized to access the datasource.

        Example:
            ```python
            schema = client.get_schema("ds-prod-123")
            for table in schema.tables:
                print(f"\n{table.name}:")
                for col in table.columns:
                    null = "NULL" if col.nullable else "NOT NULL"
                    print(f"  {col.name}: {col.data_type} {null}")
            ```
        """
        response = self._request("GET", f"/api/v1/datasources/{datasource_id}/schema")
        return self._parse_schema_response(response.json())

    async def async_get_schema(self, datasource_id: str):
        """Async version of `get_schema`.

        See `get_schema` for full documentation.
        """
        response = await self._async_request("GET", f"/api/v1/datasources/{datasource_id}/schema")
        return self._parse_schema_response(response.json())

    def _parse_schema_response(self, data: dict[str, Any]) -> Any:
        """Parse backend schema response into SDK DatasourceSchema.

        The backend returns both a hierarchical catalog structure and a flattened
        tables list for convenience. This method prefers the flattened tables.
        """
        from .types import ColumnSchema, DatasourceSchema, TableSchema

        tables = []

        # Prefer flattened tables list if available
        if "tables" in data and data["tables"]:
            for tbl in data["tables"]:
                columns = [
                    ColumnSchema(
                        name=col.get("name", ""),
                        data_type=col.get("data_type", col.get("type", "unknown")),
                        nullable=col.get("nullable", True),
                    )
                    for col in tbl.get("columns", [])
                ]
                tables.append(TableSchema(name=tbl["name"], columns=columns))
        # Fall back to extracting from catalog hierarchy
        elif "catalogs" in data:
            for catalog in data.get("catalogs", []):
                for schema in catalog.get("schemas", []):
                    schema_name = schema.get("name", "")
                    for tbl in schema.get("tables", []):
                        tbl_name = tbl.get("name", "")
                        full_name = f"{schema_name}.{tbl_name}" if schema_name else tbl_name

                        columns = [
                            ColumnSchema(
                                name=col.get("name", ""),
                                data_type=col.get("data_type", col.get("type", "unknown")),
                                nullable=col.get("nullable", True),
                            )
                            for col in tbl.get("columns", [])
                        ]
                        tables.append(TableSchema(name=full_name, columns=columns))

        return DatasourceSchema(tables=tables)

    # --- Dataset-to-Repository Mapping methods ---

    def create_repo_mapping(
        self,
        dataset_pattern: str,
        repo_owner: str,
        repo_name: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a dataset-to-repository mapping."""
        body: dict[str, Any] = {
            "dataset_pattern": dataset_pattern,
            "repo_owner": repo_owner,
            "repo_name": repo_name,
        }
        for key in ("pattern_type", "file_path", "branch", "job_name", "metadata"):
            if key in kwargs:
                body[key] = kwargs[key]
        response = self._request("POST", "/api/v1/dataset-repo-mappings", json=body)
        result: dict[str, Any] = response.json()
        return result

    def list_repo_mappings(
        self,
        source: str | None = None,
        suggestions_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List dataset-to-repository mappings."""
        if suggestions_only:
            response = self._request("GET", "/api/v1/dataset-repo-mappings/suggestions")
        else:
            params: dict[str, Any] = {}
            if source:
                params["source"] = source
            response = self._request("GET", "/api/v1/dataset-repo-mappings", params=params)
        data = response.json()
        result: list[dict[str, Any]] = data.get("items", [])
        return result

    def resolve_repo(self, dataset_id: str, include_all: bool = False) -> dict[str, Any]:
        """Resolve the repository for a dataset."""
        params: dict[str, Any] = {}
        if include_all:
            params["include_all"] = "true"
        response = self._request("GET", f"/api/v1/datasets/{dataset_id}/repo", params=params)
        result: dict[str, Any] = response.json()
        return result

    def confirm_repo_mapping(self, mapping_id: str) -> dict[str, Any]:
        """Confirm a suggested repository mapping."""
        response = self._request("POST", f"/api/v1/dataset-repo-mappings/{mapping_id}/confirm")
        result: dict[str, Any] = response.json()
        return result

    def dismiss_repo_mapping(self, mapping_id: str) -> None:
        """Dismiss a suggested repository mapping."""
        self._request("POST", f"/api/v1/dataset-repo-mappings/{mapping_id}/dismiss")

    def import_dbt_manifest(
        self,
        manifest_content: bytes,
        repo_owner: str,
        repo_name: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Import repository mappings from a dbt manifest.json."""
        params: dict[str, Any] = {
            "repo_owner": repo_owner,
            "repo_name": repo_name,
        }
        if branch:
            params["branch"] = branch
        response = self._request(
            "POST",
            "/api/v1/dataset-repo-mappings/import-dbt-manifest",
            files={"file": ("manifest.json", manifest_content, "application/json")},
            params=params,
        )
        result: dict[str, Any] = response.json()
        return result
