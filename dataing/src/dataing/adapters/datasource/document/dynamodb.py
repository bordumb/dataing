"""Amazon DynamoDB adapter implementation.

This module provides a DynamoDB adapter that implements the unified
data source interface with schema inference and scan capabilities.
"""

from __future__ import annotations

import time
from typing import Any

from dataing.adapters.datasource.document.base import DocumentAdapter
from dataing.adapters.datasource.errors import (
    AccessDeniedError,
    AuthenticationFailedError,
    ConnectionFailedError,
    QueryTimeoutError,
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

DYNAMODB_TYPE_MAP = {
    "S": NormalizedType.STRING,
    "N": NormalizedType.DECIMAL,
    "B": NormalizedType.BINARY,
    "SS": NormalizedType.ARRAY,
    "NS": NormalizedType.ARRAY,
    "BS": NormalizedType.ARRAY,
    "M": NormalizedType.MAP,
    "L": NormalizedType.ARRAY,
    "BOOL": NormalizedType.BOOLEAN,
    "NULL": NormalizedType.UNKNOWN,
}

DYNAMODB_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="connection", label="Connection", collapsed_by_default=False),
        FieldGroup(id="auth", label="AWS Credentials", collapsed_by_default=False),
        FieldGroup(id="advanced", label="Advanced", collapsed_by_default=True),
    ],
    fields=[
        ConfigField(
            name="region",
            label="AWS Region",
            type="enum",
            required=True,
            group="connection",
            default_value="us-east-1",
            options=[
                {"value": "us-east-1", "label": "US East (N. Virginia)"},
                {"value": "us-east-2", "label": "US East (Ohio)"},
                {"value": "us-west-1", "label": "US West (N. California)"},
                {"value": "us-west-2", "label": "US West (Oregon)"},
                {"value": "eu-west-1", "label": "EU (Ireland)"},
                {"value": "eu-west-2", "label": "EU (London)"},
                {"value": "eu-central-1", "label": "EU (Frankfurt)"},
                {"value": "ap-northeast-1", "label": "Asia Pacific (Tokyo)"},
                {"value": "ap-southeast-1", "label": "Asia Pacific (Singapore)"},
                {"value": "ap-southeast-2", "label": "Asia Pacific (Sydney)"},
            ],
        ),
        ConfigField(
            name="access_key_id",
            label="Access Key ID",
            type="string",
            required=True,
            group="auth",
            description="AWS Access Key ID",
        ),
        ConfigField(
            name="secret_access_key",
            label="Secret Access Key",
            type="secret",
            required=True,
            group="auth",
            description="AWS Secret Access Key",
        ),
        ConfigField(
            name="endpoint_url",
            label="Endpoint URL",
            type="string",
            required=False,
            group="advanced",
            placeholder="http://localhost:8000",
            description="Custom endpoint URL (for local DynamoDB)",
        ),
        ConfigField(
            name="table_prefix",
            label="Table Prefix",
            type="string",
            required=False,
            group="advanced",
            placeholder="prod_",
            description="Only show tables with this prefix",
        ),
    ],
)

DYNAMODB_CAPABILITIES = AdapterCapabilities(
    supports_sql=False,
    supports_sampling=True,
    supports_row_count=True,
    supports_column_stats=False,
    supports_preview=True,
    supports_write=False,
    query_language=QueryLanguage.SCAN_ONLY,
    max_concurrent_queries=5,
)


@register_adapter(
    source_type=SourceType.DYNAMODB,
    display_name="Amazon DynamoDB",
    category=SourceCategory.DATABASE,
    icon="dynamodb",
    description="Connect to Amazon DynamoDB NoSQL tables",
    capabilities=DYNAMODB_CAPABILITIES,
    config_schema=DYNAMODB_CONFIG_SCHEMA,
)
class DynamoDBAdapter(DocumentAdapter):
    """Amazon DynamoDB adapter.

    Provides schema discovery and scan capabilities for DynamoDB tables.
    Uses boto3 for AWS API access.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize DynamoDB adapter.

        Args:
            config: Configuration dictionary with:
                - region: AWS region
                - access_key_id: AWS access key
                - secret_access_key: AWS secret key
                - endpoint_url: Optional custom endpoint
                - table_prefix: Optional table name prefix filter
        """
        super().__init__(config)
        self._client: Any = None
        self._resource: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.DYNAMODB

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return DYNAMODB_CAPABILITIES

    async def connect(self) -> None:
        """Establish connection to DynamoDB."""
        try:
            import boto3
        except ImportError as e:
            raise ConnectionFailedError(
                message="boto3 is not installed. Install with: pip install boto3",
                details={"error": str(e)},
            ) from e

        try:
            session = boto3.Session(
                aws_access_key_id=self._config.get("access_key_id"),
                aws_secret_access_key=self._config.get("secret_access_key"),
                region_name=self._config.get("region", "us-east-1"),
            )

            endpoint_url = self._config.get("endpoint_url")
            if endpoint_url:
                self._client = session.client("dynamodb", endpoint_url=endpoint_url)
                self._resource = session.resource("dynamodb", endpoint_url=endpoint_url)
            else:
                self._client = session.client("dynamodb")
                self._resource = session.resource("dynamodb")

            self._connected = True
        except Exception as e:
            error_str = str(e).lower()
            if "credentials" in error_str or "access" in error_str:
                raise AuthenticationFailedError(
                    message="AWS authentication failed",
                    details={"error": str(e)},
                ) from e
            raise ConnectionFailedError(
                message=f"Failed to connect to DynamoDB: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def disconnect(self) -> None:
        """Close DynamoDB connection."""
        self._client = None
        self._resource = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test DynamoDB connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            self._client.list_tables(Limit=1)

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version="DynamoDB",
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

    async def scan_collection(
        self,
        collection: str,
        filter: dict[str, Any] | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> QueryResult:
        """Scan a DynamoDB table."""
        if not self._connected or not self._client:
            raise ConnectionFailedError(message="Not connected to DynamoDB")

        start_time = time.time()
        try:
            scan_params = {"TableName": collection, "Limit": limit}

            if filter:
                filter_expression_parts = []
                expression_values = {}
                expression_names = {}

                for i, (key, value) in enumerate(filter.items()):
                    placeholder = f":val{i}"
                    name_placeholder = f"#attr{i}"
                    filter_expression_parts.append(f"{name_placeholder} = {placeholder}")
                    expression_values[placeholder] = self._serialize_value(value)
                    expression_names[name_placeholder] = key

                if filter_expression_parts:
                    scan_params["FilterExpression"] = " AND ".join(filter_expression_parts)
                    scan_params["ExpressionAttributeValues"] = expression_values
                    scan_params["ExpressionAttributeNames"] = expression_names

            response = self._client.scan(**scan_params)
            items = response.get("Items", [])

            execution_time_ms = int((time.time() - start_time) * 1000)

            if not items:
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                )

            all_keys = set()
            for item in items:
                all_keys.update(item.keys())

            columns = [{"name": key, "data_type": "string"} for key in sorted(all_keys)]
            rows = [self._deserialize_item(item) for item in items]

            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=len(items) >= limit,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            error_str = str(e).lower()
            if "accessdenied" in error_str or "not authorized" in error_str:
                raise AccessDeniedError(message=str(e)) from e
            elif "timeout" in error_str:
                raise QueryTimeoutError(message=str(e), timeout_seconds=30) from e
            raise

    def _serialize_value(self, value: Any) -> dict[str, Any]:
        """Serialize a Python value to DynamoDB format."""
        if isinstance(value, str):
            return {"S": value}
        elif isinstance(value, bool):
            return {"BOOL": value}
        elif isinstance(value, int | float):
            return {"N": str(value)}
        elif isinstance(value, bytes):
            return {"B": value}
        elif isinstance(value, list):
            return {"L": [self._serialize_value(v) for v in value]}
        elif isinstance(value, dict):
            return {"M": {k: self._serialize_value(v) for k, v in value.items()}}
        elif value is None:
            return {"NULL": True}
        return {"S": str(value)}

    def _deserialize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Deserialize a DynamoDB item to Python dict."""
        result = {}
        for key, value in item.items():
            result[key] = self._deserialize_value(value)
        return result

    def _deserialize_value(self, value: dict[str, Any]) -> Any:
        """Deserialize a DynamoDB value."""
        if "S" in value:
            return value["S"]
        elif "N" in value:
            num_str = value["N"]
            return float(num_str) if "." in num_str else int(num_str)
        elif "B" in value:
            return value["B"]
        elif "BOOL" in value:
            return value["BOOL"]
        elif "NULL" in value:
            return None
        elif "L" in value:
            return [self._deserialize_value(v) for v in value["L"]]
        elif "M" in value:
            return {k: self._deserialize_value(v) for k, v in value["M"].items()}
        elif "SS" in value:
            return value["SS"]
        elif "NS" in value:
            return [float(n) if "." in n else int(n) for n in value["NS"]]
        elif "BS" in value:
            return value["BS"]
        return str(value)

    def _infer_type(self, value: dict[str, Any]) -> NormalizedType:
        """Infer normalized type from DynamoDB value."""
        for dynamo_type, normalized in DYNAMODB_TYPE_MAP.items():
            if dynamo_type in value:
                return normalized
        return NormalizedType.UNKNOWN

    async def sample(
        self,
        name: str,
        n: int = 100,
    ) -> QueryResult:
        """Sample documents from a DynamoDB table."""
        return await self.scan_collection(name, limit=n)

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get DynamoDB schema by listing tables and inferring column types."""
        if not self._connected or not self._client:
            raise ConnectionFailedError(message="Not connected to DynamoDB")

        try:
            tables_list = []
            exclusive_start = None
            table_prefix = self._config.get("table_prefix", "")

            while True:
                params = {"Limit": 100}
                if exclusive_start:
                    params["ExclusiveStartTableName"] = exclusive_start

                response = self._client.list_tables(**params)
                table_names = response.get("TableNames", [])

                for table_name in table_names:
                    if table_prefix and not table_name.startswith(table_prefix):
                        continue

                    if filter and filter.table_pattern:
                        if filter.table_pattern not in table_name:
                            continue

                    tables_list.append(table_name)

                exclusive_start = response.get("LastEvaluatedTableName")
                if not exclusive_start:
                    break

                if filter and filter.max_tables and len(tables_list) >= filter.max_tables:
                    tables_list = tables_list[: filter.max_tables]
                    break

            tables = []
            for table_name in tables_list:
                try:
                    desc_response = self._client.describe_table(TableName=table_name)
                    table_desc = desc_response.get("Table", {})

                    key_schema = table_desc.get("KeySchema", [])
                    pk_names = {k["AttributeName"] for k in key_schema if k["KeyType"] == "HASH"}
                    sk_names = {k["AttributeName"] for k in key_schema if k["KeyType"] == "RANGE"}

                    attr_defs = table_desc.get("AttributeDefinitions", [])
                    attr_types = {a["AttributeName"]: a["AttributeType"] for a in attr_defs}

                    columns = []
                    for attr_name, attr_type in attr_types.items():
                        columns.append(
                            {
                                "name": attr_name,
                                "data_type": DYNAMODB_TYPE_MAP.get(
                                    attr_type, NormalizedType.UNKNOWN
                                ),
                                "native_type": attr_type,
                                "nullable": attr_name not in pk_names,
                                "is_primary_key": attr_name in pk_names,
                                "is_partition_key": attr_name in sk_names,
                            }
                        )

                    scan_response = self._client.scan(TableName=table_name, Limit=10)
                    sample_items = scan_response.get("Items", [])

                    inferred_columns = set()
                    for item in sample_items:
                        for key, value in item.items():
                            if key not in attr_types and key not in inferred_columns:
                                inferred_columns.add(key)
                                columns.append(
                                    {
                                        "name": key,
                                        "data_type": self._infer_type(value),
                                        "native_type": list(value.keys())[0]
                                        if value
                                        else "UNKNOWN",
                                        "nullable": True,
                                        "is_primary_key": False,
                                        "is_partition_key": False,
                                    }
                                )

                    item_count = table_desc.get("ItemCount")
                    table_size = table_desc.get("TableSizeBytes")

                    tables.append(
                        {
                            "name": table_name,
                            "table_type": "collection",
                            "native_type": "DYNAMODB_TABLE",
                            "native_path": table_name,
                            "columns": columns,
                            "row_count": item_count,
                            "size_bytes": table_size,
                        }
                    )

                except Exception:
                    tables.append(
                        {
                            "name": table_name,
                            "table_type": "collection",
                            "native_type": "DYNAMODB_TABLE",
                            "native_path": table_name,
                            "columns": [],
                        }
                    )

            catalogs = [
                {
                    "name": "default",
                    "schemas": [
                        {
                            "name": self._config.get("region", "default"),
                            "tables": tables,
                        }
                    ],
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "dynamodb",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch DynamoDB schema: {str(e)}",
                details={"error": str(e)},
            ) from e
