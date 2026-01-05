"""Stripe API adapter implementation.

This module provides a Stripe adapter that implements the unified
data source interface with schema discovery and data querying via REST API.
"""

from __future__ import annotations

import time
from typing import Any

from dataing.adapters.datasource.api.base import APIAdapter
from dataing.adapters.datasource.errors import (
    AccessDeniedError,
    AuthenticationFailedError,
    ConnectionFailedError,
    RateLimitedError,
    SchemaFetchFailedError,
)
from dataing.adapters.datasource.registry import register_adapter
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    Column,
    ConfigField,
    ConfigSchema,
    ConnectionTestResult,
    FieldGroup,
    NormalizedType,
    QueryLanguage,
    QueryResult,
    SchemaFilter,
    SchemaResponse,
    SourceCategory,
    SourceType,
    Table,
)

STRIPE_OBJECTS: dict[str, dict[str, Any]] = {
    "customers": {
        "endpoint": "/v1/customers",
        "columns": [
            {"name": "id", "type": NormalizedType.STRING, "pk": True},
            {"name": "email", "type": NormalizedType.STRING},
            {"name": "name", "type": NormalizedType.STRING},
            {"name": "phone", "type": NormalizedType.STRING},
            {"name": "description", "type": NormalizedType.STRING},
            {"name": "created", "type": NormalizedType.TIMESTAMP},
            {"name": "currency", "type": NormalizedType.STRING},
            {"name": "default_source", "type": NormalizedType.STRING},
            {"name": "delinquent", "type": NormalizedType.BOOLEAN},
            {"name": "balance", "type": NormalizedType.INTEGER},
            {"name": "livemode", "type": NormalizedType.BOOLEAN},
            {"name": "metadata", "type": NormalizedType.JSON},
        ],
    },
    "charges": {
        "endpoint": "/v1/charges",
        "columns": [
            {"name": "id", "type": NormalizedType.STRING, "pk": True},
            {"name": "amount", "type": NormalizedType.INTEGER},
            {"name": "amount_captured", "type": NormalizedType.INTEGER},
            {"name": "amount_refunded", "type": NormalizedType.INTEGER},
            {"name": "currency", "type": NormalizedType.STRING},
            {"name": "customer", "type": NormalizedType.STRING},
            {"name": "description", "type": NormalizedType.STRING},
            {"name": "status", "type": NormalizedType.STRING},
            {"name": "created", "type": NormalizedType.TIMESTAMP},
            {"name": "paid", "type": NormalizedType.BOOLEAN},
            {"name": "refunded", "type": NormalizedType.BOOLEAN},
            {"name": "livemode", "type": NormalizedType.BOOLEAN},
            {"name": "metadata", "type": NormalizedType.JSON},
        ],
    },
    "invoices": {
        "endpoint": "/v1/invoices",
        "columns": [
            {"name": "id", "type": NormalizedType.STRING, "pk": True},
            {"name": "customer", "type": NormalizedType.STRING},
            {"name": "subscription", "type": NormalizedType.STRING},
            {"name": "status", "type": NormalizedType.STRING},
            {"name": "amount_due", "type": NormalizedType.INTEGER},
            {"name": "amount_paid", "type": NormalizedType.INTEGER},
            {"name": "amount_remaining", "type": NormalizedType.INTEGER},
            {"name": "currency", "type": NormalizedType.STRING},
            {"name": "created", "type": NormalizedType.TIMESTAMP},
            {"name": "due_date", "type": NormalizedType.TIMESTAMP},
            {"name": "paid", "type": NormalizedType.BOOLEAN},
            {"name": "livemode", "type": NormalizedType.BOOLEAN},
            {"name": "metadata", "type": NormalizedType.JSON},
        ],
    },
    "subscriptions": {
        "endpoint": "/v1/subscriptions",
        "columns": [
            {"name": "id", "type": NormalizedType.STRING, "pk": True},
            {"name": "customer", "type": NormalizedType.STRING},
            {"name": "status", "type": NormalizedType.STRING},
            {"name": "current_period_start", "type": NormalizedType.TIMESTAMP},
            {"name": "current_period_end", "type": NormalizedType.TIMESTAMP},
            {"name": "cancel_at_period_end", "type": NormalizedType.BOOLEAN},
            {"name": "canceled_at", "type": NormalizedType.TIMESTAMP},
            {"name": "created", "type": NormalizedType.TIMESTAMP},
            {"name": "livemode", "type": NormalizedType.BOOLEAN},
            {"name": "metadata", "type": NormalizedType.JSON},
        ],
    },
    "products": {
        "endpoint": "/v1/products",
        "columns": [
            {"name": "id", "type": NormalizedType.STRING, "pk": True},
            {"name": "name", "type": NormalizedType.STRING},
            {"name": "description", "type": NormalizedType.STRING},
            {"name": "active", "type": NormalizedType.BOOLEAN},
            {"name": "created", "type": NormalizedType.TIMESTAMP},
            {"name": "updated", "type": NormalizedType.TIMESTAMP},
            {"name": "livemode", "type": NormalizedType.BOOLEAN},
            {"name": "metadata", "type": NormalizedType.JSON},
        ],
    },
    "prices": {
        "endpoint": "/v1/prices",
        "columns": [
            {"name": "id", "type": NormalizedType.STRING, "pk": True},
            {"name": "product", "type": NormalizedType.STRING},
            {"name": "unit_amount", "type": NormalizedType.INTEGER},
            {"name": "currency", "type": NormalizedType.STRING},
            {"name": "type", "type": NormalizedType.STRING},
            {"name": "recurring", "type": NormalizedType.JSON},
            {"name": "active", "type": NormalizedType.BOOLEAN},
            {"name": "created", "type": NormalizedType.TIMESTAMP},
            {"name": "livemode", "type": NormalizedType.BOOLEAN},
            {"name": "metadata", "type": NormalizedType.JSON},
        ],
    },
    "payment_intents": {
        "endpoint": "/v1/payment_intents",
        "columns": [
            {"name": "id", "type": NormalizedType.STRING, "pk": True},
            {"name": "amount", "type": NormalizedType.INTEGER},
            {"name": "amount_received", "type": NormalizedType.INTEGER},
            {"name": "currency", "type": NormalizedType.STRING},
            {"name": "customer", "type": NormalizedType.STRING},
            {"name": "status", "type": NormalizedType.STRING},
            {"name": "created", "type": NormalizedType.TIMESTAMP},
            {"name": "livemode", "type": NormalizedType.BOOLEAN},
            {"name": "metadata", "type": NormalizedType.JSON},
        ],
    },
    "refunds": {
        "endpoint": "/v1/refunds",
        "columns": [
            {"name": "id", "type": NormalizedType.STRING, "pk": True},
            {"name": "amount", "type": NormalizedType.INTEGER},
            {"name": "charge", "type": NormalizedType.STRING},
            {"name": "currency", "type": NormalizedType.STRING},
            {"name": "status", "type": NormalizedType.STRING},
            {"name": "reason", "type": NormalizedType.STRING},
            {"name": "created", "type": NormalizedType.TIMESTAMP},
            {"name": "metadata", "type": NormalizedType.JSON},
        ],
    },
    "balance_transactions": {
        "endpoint": "/v1/balance_transactions",
        "columns": [
            {"name": "id", "type": NormalizedType.STRING, "pk": True},
            {"name": "amount", "type": NormalizedType.INTEGER},
            {"name": "currency", "type": NormalizedType.STRING},
            {"name": "fee", "type": NormalizedType.INTEGER},
            {"name": "net", "type": NormalizedType.INTEGER},
            {"name": "type", "type": NormalizedType.STRING},
            {"name": "status", "type": NormalizedType.STRING},
            {"name": "created", "type": NormalizedType.TIMESTAMP},
        ],
    },
    "payouts": {
        "endpoint": "/v1/payouts",
        "columns": [
            {"name": "id", "type": NormalizedType.STRING, "pk": True},
            {"name": "amount", "type": NormalizedType.INTEGER},
            {"name": "currency", "type": NormalizedType.STRING},
            {"name": "status", "type": NormalizedType.STRING},
            {"name": "arrival_date", "type": NormalizedType.TIMESTAMP},
            {"name": "created", "type": NormalizedType.TIMESTAMP},
            {"name": "livemode", "type": NormalizedType.BOOLEAN},
            {"name": "metadata", "type": NormalizedType.JSON},
        ],
    },
}

STRIPE_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="auth", label="Authentication", collapsed_by_default=False),
        FieldGroup(id="advanced", label="Advanced", collapsed_by_default=True),
    ],
    fields=[
        ConfigField(
            name="api_key",
            label="Secret API Key",
            type="secret",
            required=True,
            group="auth",
            placeholder="sk_live_... or sk_test_...",
            description="Stripe secret API key (starts with sk_live_ or sk_test_)",
            help_url="https://stripe.com/docs/keys",
        ),
        ConfigField(
            name="objects",
            label="Objects to Include",
            type="string",
            required=False,
            group="advanced",
            placeholder="customers,charges,invoices",
            description="Comma-separated list of objects (default: all standard objects)",
        ),
    ],
)

STRIPE_CAPABILITIES = AdapterCapabilities(
    supports_sql=False,
    supports_sampling=True,
    supports_row_count=False,
    supports_column_stats=False,
    supports_preview=True,
    supports_write=False,
    query_language=QueryLanguage.SCAN_ONLY,
    rate_limit_requests_per_minute=100,
    max_concurrent_queries=1,
)


@register_adapter(
    source_type=SourceType.STRIPE,
    display_name="Stripe",
    category=SourceCategory.API,
    icon="stripe",
    description="Connect to Stripe payment data via REST API",
    capabilities=STRIPE_CAPABILITIES,
    config_schema=STRIPE_CONFIG_SCHEMA,
)
class StripeAdapter(APIAdapter):
    """Stripe API adapter.

    Provides schema discovery and data querying for Stripe payment objects.
    Uses the Stripe REST API with API key authentication.
    """

    BASE_URL = "https://api.stripe.com"

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Stripe adapter.

        Args:
            config: Configuration dictionary with:
                - api_key: Stripe secret API key
                - objects: Comma-separated list of objects to include (optional)
        """
        super().__init__(config)
        self._session: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.STRIPE

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return STRIPE_CAPABILITIES

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self._config.get('api_key', '')}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    async def connect(self) -> None:
        """Establish connection to Stripe API."""
        try:
            import httpx
        except ImportError as e:
            raise ConnectionFailedError(
                message="httpx is not installed. Install with: pip install httpx",
                details={"error": str(e)},
            ) from e

        try:
            self._session = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=self._get_headers(),
                timeout=30.0,
            )
            self._connected = True
        except Exception as e:
            raise ConnectionFailedError(
                message=f"Failed to initialize Stripe client: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def disconnect(self) -> None:
        """Close Stripe connection."""
        if self._session:
            await self._session.aclose()
            self._session = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test Stripe API connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            response = await self._session.get("/v1/balance")
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                api_key = self._config.get("api_key", "")
                mode = "Test" if "test" in api_key else "Live"
                return ConnectionTestResult(
                    success=True,
                    latency_ms=latency_ms,
                    server_version=f"Stripe API ({mode} mode)",
                    message="Connection successful",
                )
            elif response.status_code == 401:
                return ConnectionTestResult(
                    success=False,
                    latency_ms=latency_ms,
                    message="Invalid API key",
                    error_code="AUTHENTICATION_FAILED",
                )
            else:
                return ConnectionTestResult(
                    success=False,
                    latency_ms=latency_ms,
                    message=f"API error: {response.status_code}",
                    error_code="CONNECTION_FAILED",
                )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=False,
                latency_ms=latency_ms,
                message=str(e),
                error_code="CONNECTION_FAILED",
            )

    async def list_objects(self) -> list[str]:
        """List available Stripe objects."""
        objects_config = self._config.get("objects", "")
        if objects_config:
            return [o.strip() for o in objects_config.split(",")]
        return list(STRIPE_OBJECTS.keys())

    async def describe_object(self, object_name: str) -> Table:
        """Get schema for a Stripe object."""
        obj_def = STRIPE_OBJECTS.get(object_name)
        if not obj_def:
            return Table(
                name=object_name,
                table_type="object",
                native_type="STRIPE_OBJECT",
                native_path=object_name,
                columns=[],
            )

        columns = []
        for col in obj_def["columns"]:
            columns.append(
                Column(
                    name=col["name"],
                    data_type=col["type"],
                    native_type=col["type"].value,
                    nullable=not col.get("pk", False),
                    is_primary_key=col.get("pk", False),
                    is_partition_key=False,
                )
            )

        return Table(
            name=object_name,
            table_type="object",
            native_type="STRIPE_OBJECT",
            native_path=object_name,
            columns=columns,
        )

    async def query_object(
        self,
        object_name: str,
        query: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Query records from a Stripe object."""
        if not self._connected or not self._session:
            raise ConnectionFailedError(message="Not connected to Stripe")

        obj_def = STRIPE_OBJECTS.get(object_name)
        if not obj_def:
            raise ConnectionFailedError(message=f"Unknown Stripe object: {object_name}")

        start_time = time.time()
        try:
            response = await self._session.get(
                obj_def["endpoint"],
                params={"limit": min(limit, 100)},
            )

            if response.status_code == 401:
                raise AuthenticationFailedError(message="Invalid Stripe API key")
            elif response.status_code == 403:
                raise AccessDeniedError(message=f"Access denied to {object_name}")
            elif response.status_code == 429:
                raise RateLimitedError(
                    message="Stripe API rate limit exceeded",
                    retry_after_seconds=1,
                )

            response.raise_for_status()
            data = response.json()

            execution_time_ms = int((time.time() - start_time) * 1000)
            results = data.get("data", [])

            if not results:
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                )

            col_names = [c["name"] for c in obj_def["columns"]]
            columns = [{"name": name, "data_type": "string"} for name in col_names]

            rows = []
            for record in results:
                row = {}
                for col_name in col_names:
                    value = record.get(col_name)
                    if isinstance(value, dict):
                        row[col_name] = value
                    else:
                        row[col_name] = value
                rows.append(row)

            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=data.get("has_more", False),
                execution_time_ms=execution_time_ms,
            )

        except (AuthenticationFailedError, AccessDeniedError, RateLimitedError):
            raise
        except Exception as e:
            raise ConnectionFailedError(
                message=f"Failed to query {object_name}: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get Stripe schema."""
        if not self._connected or not self._session:
            raise ConnectionFailedError(message="Not connected to Stripe")

        try:
            objects = await self.list_objects()

            if filter and filter.table_pattern:
                objects = [o for o in objects if filter.table_pattern in o]

            if filter and filter.max_tables:
                objects = objects[: filter.max_tables]

            tables = []
            for obj_name in objects:
                table_def = await self.describe_object(obj_name)
                tables.append(table_def)

            catalogs = [
                {
                    "name": "default",
                    "schemas": [
                        {
                            "name": "payments",
                            "tables": tables,
                        }
                    ],
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "stripe",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch Stripe schema: {str(e)}",
                details={"error": str(e)},
            ) from e
