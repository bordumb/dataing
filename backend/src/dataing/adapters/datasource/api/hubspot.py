"""HubSpot API adapter implementation.

This module provides a HubSpot adapter that implements the unified
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
)

HUBSPOT_TYPE_MAP = {
    "string": NormalizedType.STRING,
    "number": NormalizedType.DECIMAL,
    "date": NormalizedType.DATE,
    "datetime": NormalizedType.TIMESTAMP,
    "enumeration": NormalizedType.STRING,
    "bool": NormalizedType.BOOLEAN,
    "phone_number": NormalizedType.STRING,
    "email": NormalizedType.STRING,
}

HUBSPOT_OBJECTS = [
    "contacts",
    "companies",
    "deals",
    "tickets",
    "products",
    "line_items",
    "quotes",
    "calls",
    "emails",
    "meetings",
    "notes",
    "tasks",
]

HUBSPOT_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="auth", label="Authentication", collapsed_by_default=False),
        FieldGroup(id="advanced", label="Advanced", collapsed_by_default=True),
    ],
    fields=[
        ConfigField(
            name="access_token",
            label="Private App Access Token",
            type="secret",
            required=True,
            group="auth",
            description="HubSpot Private App access token",
            help_url="https://developers.hubspot.com/docs/api/private-apps",
        ),
        ConfigField(
            name="objects",
            label="Objects to Include",
            type="string",
            required=False,
            group="advanced",
            placeholder="contacts,companies,deals",
            description="Comma-separated list of objects (default: all standard objects)",
        ),
    ],
)

HUBSPOT_CAPABILITIES = AdapterCapabilities(
    supports_sql=False,
    supports_sampling=True,
    supports_row_count=True,
    supports_column_stats=False,
    supports_preview=True,
    supports_write=False,
    query_language=QueryLanguage.SCAN_ONLY,
    rate_limit_requests_per_minute=100,
    max_concurrent_queries=1,
)


@register_adapter(
    source_type=SourceType.HUBSPOT,
    display_name="HubSpot",
    category=SourceCategory.API,
    icon="hubspot",
    description="Connect to HubSpot CRM data via REST API",
    capabilities=HUBSPOT_CAPABILITIES,
    config_schema=HUBSPOT_CONFIG_SCHEMA,
)
class HubSpotAdapter(APIAdapter):
    """HubSpot API adapter.

    Provides schema discovery and data querying for HubSpot CRM objects.
    Uses the HubSpot REST API with Private App authentication.
    """

    BASE_URL = "https://api.hubapi.com"

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize HubSpot adapter.

        Args:
            config: Configuration dictionary with:
                - access_token: Private App access token
                - objects: Comma-separated list of objects to include (optional)
        """
        super().__init__(config)
        self._session: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.HUBSPOT

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return HUBSPOT_CAPABILITIES

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self._config.get('access_token', '')}",
            "Content-Type": "application/json",
        }

    async def connect(self) -> None:
        """Establish connection to HubSpot API."""
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
                message=f"Failed to initialize HubSpot client: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def disconnect(self) -> None:
        """Close HubSpot connection."""
        if self._session:
            await self._session.aclose()
            self._session = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test HubSpot API connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            response = await self._session.get("/crm/v3/objects/contacts?limit=1")
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                return ConnectionTestResult(
                    success=True,
                    latency_ms=latency_ms,
                    server_version="HubSpot API v3",
                    message="Connection successful",
                )
            elif response.status_code == 401:
                return ConnectionTestResult(
                    success=False,
                    latency_ms=latency_ms,
                    message="Invalid access token",
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
        """List available HubSpot objects."""
        objects_config = self._config.get("objects", "")
        if objects_config:
            return [o.strip() for o in objects_config.split(",")]
        return HUBSPOT_OBJECTS

    async def describe_object(self, object_name: str) -> dict[str, Any]:
        """Get schema for a HubSpot object."""
        if not self._connected or not self._session:
            raise ConnectionFailedError(message="Not connected to HubSpot")

        try:
            response = await self._session.get(f"/crm/v3/properties/{object_name}")

            if response.status_code == 401:
                raise AuthenticationFailedError(message="Invalid HubSpot access token")
            elif response.status_code == 403:
                raise AccessDeniedError(message=f"Access denied to {object_name} properties")
            elif response.status_code == 429:
                raise RateLimitedError(
                    message="HubSpot API rate limit exceeded",
                    retry_after_seconds=10,
                )

            response.raise_for_status()
            data = response.json()

            columns = []
            for prop in data.get("results", []):
                prop_type = prop.get("type", "string")
                columns.append(
                    {
                        "name": prop.get("name"),
                        "data_type": HUBSPOT_TYPE_MAP.get(prop_type, NormalizedType.STRING),
                        "native_type": prop_type,
                        "nullable": True,
                        "is_primary_key": prop.get("name") == "hs_object_id",
                        "is_partition_key": False,
                        "description": prop.get("label"),
                    }
                )

            return {
                "name": object_name,
                "table_type": "object",
                "native_type": "HUBSPOT_OBJECT",
                "native_path": object_name,
                "columns": columns,
            }

        except (AuthenticationFailedError, AccessDeniedError, RateLimitedError):
            raise
        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to describe {object_name}: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def query_object(
        self,
        object_name: str,
        limit: int = 100,
        properties: list[str] | None = None,
    ) -> QueryResult:
        """Query records from a HubSpot object."""
        if not self._connected or not self._session:
            raise ConnectionFailedError(message="Not connected to HubSpot")

        start_time = time.time()
        try:
            params: dict[str, Any] = {"limit": min(limit, 100)}
            if properties:
                params["properties"] = ",".join(properties)

            response = await self._session.get(
                f"/crm/v3/objects/{object_name}",
                params=params,
            )

            if response.status_code == 401:
                raise AuthenticationFailedError(message="Invalid HubSpot access token")
            elif response.status_code == 403:
                raise AccessDeniedError(message=f"Access denied to {object_name}")
            elif response.status_code == 429:
                raise RateLimitedError(
                    message="HubSpot API rate limit exceeded",
                    retry_after_seconds=10,
                )

            response.raise_for_status()
            data = response.json()

            execution_time_ms = int((time.time() - start_time) * 1000)
            results = data.get("results", [])

            if not results:
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                )

            all_keys = set()
            rows = []
            for record in results:
                props = record.get("properties", {})
                props["id"] = record.get("id")
                all_keys.update(props.keys())
                rows.append(props)

            columns = [{"name": key, "data_type": "string"} for key in sorted(all_keys)]

            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=data.get("paging") is not None,
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
        """Get HubSpot schema."""
        if not self._connected or not self._session:
            raise ConnectionFailedError(message="Not connected to HubSpot")

        try:
            objects = await self.list_objects()

            if filter and filter.table_pattern:
                objects = [o for o in objects if filter.table_pattern in o]

            if filter and filter.max_tables:
                objects = objects[: filter.max_tables]

            tables = []
            for obj_name in objects:
                try:
                    table_def = await self.describe_object(obj_name)
                    tables.append(table_def)
                except Exception:
                    tables.append(
                        {
                            "name": obj_name,
                            "table_type": "object",
                            "native_type": "HUBSPOT_OBJECT",
                            "native_path": obj_name,
                            "columns": [],
                        }
                    )

            catalogs = [
                {
                    "name": "default",
                    "schemas": [
                        {
                            "name": "crm",
                            "tables": tables,
                        }
                    ],
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "hubspot",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch HubSpot schema: {str(e)}",
                details={"error": str(e)},
            ) from e
