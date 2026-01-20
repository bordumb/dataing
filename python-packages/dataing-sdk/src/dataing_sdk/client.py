"""Dataing API client."""

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

    Supports both synchronous and asynchronous methods. By default, uses
    synchronous HTTP calls. For async usage, use the async_* methods.

    Example:
        # Sync usage
        client = DataingClient(api_key="your-key")
        bundle = client.create_bundle(assets=[...])

        # Async usage
        async with client:
            bundle = await client.async_create_bundle(assets=[...])
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the Dataing client.

        Args:
            base_url: Base URL of the Dataing API. Defaults to DATAING_BASE_URL
                env var or http://localhost:8000.
            api_key: API key for authentication. Defaults to DATAING_API_KEY env var.
            timeout: Request timeout in seconds.

        Raises:
            AuthError: If no API key is provided and DATAING_API_KEY is not set.
        """
        self.base_url = (base_url or os.environ.get(ENV_BASE_URL, "http://localhost:8000")).rstrip(
            "/"
        )
        self.api_key = api_key or os.environ.get(ENV_API_KEY)
        self.timeout = timeout

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

    def __enter__(self) -> "DataingClient":
        """Enter context manager for sync usage."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager for sync usage."""
        self.close()

    async def __aenter__(self) -> "DataingClient":
        """Enter context manager for async usage."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit context manager for async usage."""
        await self.aclose()

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

        Args:
            assets: List of assets to include in the bundle.
            window: Optional time window for context (e.g., "7d", "24h").
            include_lineage: Include lineage graph in response.
            include_operational: Include operational facts in response.
            include_anomalies: Include anomaly summaries in response.

        Returns:
            ContextBundle with resolved assets and context.
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
        """Async version of create_bundle."""
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

        Convenience method that creates a bundle and wraps it in a Context object.

        Args:
            *urns: URN strings (e.g., "postgres://db.schema.table").
            assets: List of AssetRef objects (alternative to URNs).
            window: Optional time window for context.

        Returns:
            Context object with resolved assets and context data.

        Example:
            ctx = client.context("postgres://db.schema.orders")
            ctx = client.context(
                "postgres://db.schema.orders",
                "postgres://db.schema.customers"
            )
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
        """Async version of context()."""
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

    # --- Run methods (stub for fn-17.6) ---

    def run(
        self,
        assets: list[AssetRef],
        goal: str,
        bundle_id: str | None = None,
    ) -> Run:
        """Create and start an investigation run.

        This is the one-call API that resolves assets, creates a bundle,
        and starts the run in a single operation.

        Stub implementation. Full implementation in fn-17.6.

        Args:
            assets: List of assets to investigate.
            goal: Investigation goal/question.
            bundle_id: Optional existing bundle ID to use.

        Returns:
            Run object with run_id and status.
        """
        raise NotImplementedError("Full implementation in fn-17.6")

    async def async_run(
        self,
        assets: list[AssetRef],
        goal: str,
        bundle_id: str | None = None,
    ) -> Run:
        """Async version of run."""
        raise NotImplementedError("Full implementation in fn-17.6")

    # --- Health check ---

    def health(self) -> dict[str, Any]:
        """Check API health.

        Returns:
            Health status dict.
        """
        response = self._request("GET", "/health")
        return response.json()

    async def async_health(self) -> dict[str, Any]:
        """Async version of health check."""
        response = await self._async_request("GET", "/health")
        return response.json()
