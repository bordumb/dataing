"""Salesforce adapter implementation.

This module provides a Salesforce adapter that implements the unified
data source interface with SOQL querying and object discovery.
"""

from __future__ import annotations

import time
from typing import Any

from dataing.adapters.datasource.api.base import APIAdapter
from dataing.adapters.datasource.errors import (
    AuthenticationFailedError,
    ConnectionFailedError,
    QuerySyntaxError,
    RateLimitedError,
    SchemaFetchFailedError,
)
from dataing.adapters.datasource.registry import register_adapter
from dataing.adapters.datasource.type_mapping import normalize_type
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    Column,
    ConfigField,
    ConfigSchema,
    ConnectionTestResult,
    FieldGroup,
    QueryLanguage,
    QueryResult,
    SchemaFilter,
    SchemaResponse,
    SourceCategory,
    SourceType,
    Table,
)

SALESFORCE_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="connection", label="Connection", collapsed_by_default=False),
        FieldGroup(id="oauth", label="OAuth Credentials", collapsed_by_default=False),
    ],
    fields=[
        ConfigField(
            name="instance_url",
            label="Instance URL",
            type="string",
            required=True,
            group="connection",
            placeholder="https://yourcompany.salesforce.com",
            pattern="^https://.*\\.salesforce\\.com$",
        ),
        ConfigField(
            name="auth_type",
            label="Authentication Type",
            type="enum",
            required=True,
            group="oauth",
            default_value="password",
            options=[
                {"value": "oauth", "label": "OAuth 2.0 (Recommended)"},
                {"value": "password", "label": "Username/Password"},
            ],
        ),
        ConfigField(
            name="client_id",
            label="Consumer Key",
            type="string",
            required=False,
            group="oauth",
            show_if={"field": "auth_type", "value": "oauth"},
        ),
        ConfigField(
            name="client_secret",
            label="Consumer Secret",
            type="secret",
            required=False,
            group="oauth",
            show_if={"field": "auth_type", "value": "oauth"},
        ),
        ConfigField(
            name="refresh_token",
            label="Refresh Token",
            type="secret",
            required=False,
            group="oauth",
            show_if={"field": "auth_type", "value": "oauth"},
        ),
        ConfigField(
            name="username",
            label="Username",
            type="string",
            required=False,
            group="oauth",
            show_if={"field": "auth_type", "value": "password"},
        ),
        ConfigField(
            name="password",
            label="Password",
            type="secret",
            required=False,
            group="oauth",
            show_if={"field": "auth_type", "value": "password"},
        ),
        ConfigField(
            name="security_token",
            label="Security Token",
            type="secret",
            required=False,
            group="oauth",
            show_if={"field": "auth_type", "value": "password"},
        ),
    ],
)

SALESFORCE_CAPABILITIES = AdapterCapabilities(
    supports_sql=False,
    supports_sampling=True,
    supports_row_count=True,
    supports_column_stats=False,
    supports_preview=True,
    supports_write=False,
    rate_limit_requests_per_minute=100,
    max_concurrent_queries=1,
    query_language=QueryLanguage.SOQL,
)


@register_adapter(
    source_type=SourceType.SALESFORCE,
    display_name="Salesforce",
    category=SourceCategory.API,
    icon="salesforce",
    description="Connect to Salesforce for CRM data querying via SOQL",
    capabilities=SALESFORCE_CAPABILITIES,
    config_schema=SALESFORCE_CONFIG_SCHEMA,
)
class SalesforceAdapter(APIAdapter):
    """Salesforce API adapter.

    Provides SOQL querying and object schema discovery for Salesforce.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Salesforce adapter.

        Args:
            config: Configuration dictionary with:
                - instance_url: Salesforce instance URL
                - auth_type: 'oauth' or 'password'
                - For OAuth: client_id, client_secret, refresh_token
                - For password: username, password, security_token
        """
        super().__init__(config)
        self._sf: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.SALESFORCE

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return SALESFORCE_CAPABILITIES

    async def connect(self) -> None:
        """Establish connection to Salesforce."""
        try:
            from simple_salesforce import Salesforce
        except ImportError as e:
            raise ConnectionFailedError(
                message="simple-salesforce not installed. Install: pip install simple-salesforce",
                details={"error": str(e)},
            ) from e

        try:
            auth_type = self._config.get("auth_type", "password")
            instance_url = self._config.get("instance_url", "")

            # Extract domain from instance URL
            domain = instance_url.replace("https://", "").replace(".salesforce.com", "")

            if auth_type == "oauth":
                client_id = self._config.get("client_id", "")
                client_secret = self._config.get("client_secret", "")
                refresh_token = self._config.get("refresh_token", "")

                self._sf = Salesforce(
                    instance_url=instance_url,
                    consumer_key=client_id,
                    consumer_secret=client_secret,
                    refresh_token=refresh_token,
                )
            else:
                username = self._config.get("username", "")
                password = self._config.get("password", "")
                security_token = self._config.get("security_token", "")

                self._sf = Salesforce(
                    username=username,
                    password=password,
                    security_token=security_token,
                    domain=domain if "sandbox" in domain else None,
                )

            self._connected = True
        except Exception as e:
            error_str = str(e).lower()
            if "invalid_grant" in error_str or "authentication" in error_str:
                raise AuthenticationFailedError(
                    message="Salesforce authentication failed",
                    details={"error": str(e)},
                ) from e
            else:
                raise ConnectionFailedError(
                    message=f"Failed to connect to Salesforce: {str(e)}",
                    details={"error": str(e)},
                ) from e

    async def disconnect(self) -> None:
        """Close Salesforce connection."""
        self._sf = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test Salesforce connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            # Query organization info
            org_info = self._sf.query("SELECT Id, Name FROM Organization LIMIT 1")
            org_name = org_info.get("records", [{}])[0].get("Name", "Unknown")

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version=f"Salesforce ({org_name})",
                message="Connection successful",
            )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=False,
                latency_ms=latency_ms,
                message=str(e),
                error_code="CONNECTION_FAILED",
            )

    async def query_object(
        self,
        object_name: str,
        query: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Query a Salesforce object using SOQL."""
        if not self._connected or not self._sf:
            raise ConnectionFailedError(message="Not connected to Salesforce")

        start_time = time.time()
        try:
            if query:
                soql = query
            else:
                # Build default query
                desc = self._sf.__getattr__(object_name).describe()
                fields = [f["name"] for f in desc["fields"][:50]]  # Limit fields
                soql = f"SELECT {', '.join(fields)} FROM {object_name} LIMIT {limit}"

            result = self._sf.query(soql)
            records = result.get("records", [])

            execution_time_ms = int((time.time() - start_time) * 1000)

            if not records:
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                )

            # Get columns from first record
            columns = []
            if records:
                first = records[0]
                for key in first.keys():
                    if key != "attributes":
                        columns.append({"name": key, "data_type": "string"})

            # Convert records to rows
            row_dicts = []
            for record in records:
                row = {}
                for key, value in record.items():
                    if key != "attributes":
                        row[key] = self._serialize_value(value)
                row_dicts.append(row)

            return QueryResult(
                columns=columns,
                rows=row_dicts,
                row_count=len(row_dicts),
                truncated=result.get("done", True) is False,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            error_str = str(e).lower()
            if "malformed query" in error_str or "syntax" in error_str:
                raise QuerySyntaxError(
                    message=str(e),
                    query=query[:200] if query else object_name,
                ) from e
            elif "request_limit_exceeded" in error_str:
                raise RateLimitedError(
                    message="Salesforce API rate limit exceeded",
                    retry_after_seconds=60,
                ) from e
            else:
                raise

    def _serialize_value(self, value: Any) -> Any:
        """Convert Salesforce values to JSON-serializable format."""
        if isinstance(value, dict):
            # Nested object reference
            if "attributes" in value:
                return {k: self._serialize_value(v) for k, v in value.items() if k != "attributes"}
            return value
        return value

    async def describe_object(
        self,
        object_name: str,
    ) -> Table:
        """Get the schema of a Salesforce object."""
        if not self._connected or not self._sf:
            raise ConnectionFailedError(message="Not connected to Salesforce")

        desc = self._sf.__getattr__(object_name).describe()

        columns = []
        for field in desc["fields"]:
            normalized_type = normalize_type(field["type"], SourceType.SALESFORCE)
            columns.append(
                Column(
                    name=field["name"],
                    data_type=normalized_type,
                    native_type=field["type"],
                    nullable=field.get("nillable", True),
                    is_primary_key=field.get("name") == "Id",
                    is_partition_key=False,
                    description=field.get("label"),
                )
            )

        return Table(
            name=object_name,
            table_type="object",
            native_type="SALESFORCE_OBJECT",
            native_path=object_name,
            columns=columns,
            description=desc.get("label"),
        )

    async def list_objects(self) -> list[str]:
        """List all Salesforce objects."""
        if not self._connected or not self._sf:
            raise ConnectionFailedError(message="Not connected to Salesforce")

        sobjects = self._sf.describe()["sobjects"]
        return [obj["name"] for obj in sobjects if obj.get("queryable", False)]

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get Salesforce schema (queryable objects)."""
        if not self._connected or not self._sf:
            raise ConnectionFailedError(message="Not connected to Salesforce")

        try:
            # List all objects
            object_names = await self.list_objects()

            # Apply filter if provided
            if filter and filter.table_pattern:
                import fnmatch

                pattern = filter.table_pattern.replace("%", "*")
                object_names = [o for o in object_names if fnmatch.fnmatch(o, pattern)]

            # Limit objects
            max_tables = filter.max_tables if filter else 100
            object_names = object_names[:max_tables]

            # Get schema for each object
            tables = []
            for obj_name in object_names:
                try:
                    table = await self.describe_object(obj_name)
                    tables.append(
                        {
                            "name": table.name,
                            "table_type": table.table_type,
                            "native_type": table.native_type,
                            "native_path": table.native_path,
                            "columns": [
                                {
                                    "name": col.name,
                                    "data_type": col.data_type,
                                    "native_type": col.native_type,
                                    "nullable": col.nullable,
                                    "is_primary_key": col.is_primary_key,
                                    "is_partition_key": col.is_partition_key,
                                    "description": col.description,
                                }
                                for col in table.columns
                            ],
                            "description": table.description,
                        }
                    )
                except Exception:
                    # Skip objects we can't describe
                    continue

            # Build catalog structure
            catalogs = [
                {
                    "name": "default",
                    "schemas": [
                        {
                            "name": "salesforce",
                            "tables": tables,
                        }
                    ],
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "salesforce",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch Salesforce schema: {str(e)}",
                details={"error": str(e)},
            ) from e
