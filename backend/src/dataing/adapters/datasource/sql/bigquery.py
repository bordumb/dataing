"""BigQuery adapter implementation.

This module provides a BigQuery adapter that implements the unified
data source interface with full schema discovery and query capabilities.
"""

from __future__ import annotations

import time
from typing import Any

from dataing.adapters.datasource.errors import (
    AccessDeniedError,
    AuthenticationFailedError,
    ConnectionFailedError,
    QuerySyntaxError,
    QueryTimeoutError,
    SchemaFetchFailedError,
)
from dataing.adapters.datasource.registry import register_adapter
from dataing.adapters.datasource.sql.base import SQLAdapter
from dataing.adapters.datasource.type_mapping import normalize_type
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
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
)

BIGQUERY_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="project", label="Project", collapsed_by_default=False),
        FieldGroup(id="auth", label="Authentication", collapsed_by_default=False),
        FieldGroup(id="advanced", label="Advanced", collapsed_by_default=True),
    ],
    fields=[
        ConfigField(
            name="project_id",
            label="Project ID",
            type="string",
            required=True,
            group="project",
            placeholder="my-gcp-project",
            description="Google Cloud project ID",
        ),
        ConfigField(
            name="dataset",
            label="Default Dataset",
            type="string",
            required=False,
            group="project",
            placeholder="my_dataset",
            description="Default dataset to query (optional)",
        ),
        ConfigField(
            name="credentials_json",
            label="Service Account JSON",
            type="secret",
            required=True,
            group="auth",
            description="Service account credentials JSON (paste full JSON)",
        ),
        ConfigField(
            name="location",
            label="Location",
            type="enum",
            required=False,
            group="advanced",
            default_value="US",
            options=[
                {"value": "US", "label": "US (multi-region)"},
                {"value": "EU", "label": "EU (multi-region)"},
                {"value": "us-central1", "label": "us-central1"},
                {"value": "us-east1", "label": "us-east1"},
                {"value": "europe-west1", "label": "europe-west1"},
                {"value": "asia-east1", "label": "asia-east1"},
            ],
        ),
        ConfigField(
            name="query_timeout",
            label="Query Timeout (seconds)",
            type="integer",
            required=False,
            group="advanced",
            default_value=300,
            min_value=30,
            max_value=3600,
        ),
    ],
)

BIGQUERY_CAPABILITIES = AdapterCapabilities(
    supports_sql=True,
    supports_sampling=True,
    supports_row_count=True,
    supports_column_stats=True,
    supports_preview=True,
    supports_write=False,
    query_language=QueryLanguage.SQL,
    max_concurrent_queries=5,
)


@register_adapter(
    source_type=SourceType.BIGQUERY,
    display_name="BigQuery",
    category=SourceCategory.DATABASE,
    icon="bigquery",
    description="Connect to Google BigQuery for serverless data warehouse querying",
    capabilities=BIGQUERY_CAPABILITIES,
    config_schema=BIGQUERY_CONFIG_SCHEMA,
)
class BigQueryAdapter(SQLAdapter):
    """BigQuery database adapter.

    Provides full schema discovery and query execution for BigQuery.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize BigQuery adapter.

        Args:
            config: Configuration dictionary with:
                - project_id: GCP project ID
                - dataset: Default dataset (optional)
                - credentials_json: Service account JSON
                - location: Data location (optional)
                - query_timeout: Timeout in seconds (optional)
        """
        super().__init__(config)
        self._client: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.BIGQUERY

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return BIGQUERY_CAPABILITIES

    async def connect(self) -> None:
        """Establish connection to BigQuery."""
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account
        except ImportError as e:
            raise ConnectionFailedError(
                message="google-cloud-bigquery not installed. pip install google-cloud-bigquery",
                details={"error": str(e)},
            ) from e

        try:
            import json

            project_id = self._config.get("project_id", "")
            credentials_json = self._config.get("credentials_json", "")
            location = self._config.get("location", "US")

            # Parse credentials JSON
            if isinstance(credentials_json, str):
                credentials_info = json.loads(credentials_json)
            else:
                credentials_info = credentials_json

            credentials = service_account.Credentials.from_service_account_info(credentials_info)

            self._client = bigquery.Client(
                project=project_id,
                credentials=credentials,
                location=location,
            )
            self._connected = True
        except json.JSONDecodeError as e:
            raise AuthenticationFailedError(
                message="Invalid credentials JSON format",
                details={"error": str(e)},
            ) from e
        except Exception as e:
            error_str = str(e).lower()
            if "permission" in error_str or "forbidden" in error_str or "403" in error_str:
                raise AccessDeniedError(
                    message="Access denied to BigQuery project",
                ) from e
            elif "invalid" in error_str and "credential" in error_str:
                raise AuthenticationFailedError(
                    message="Invalid BigQuery credentials",
                    details={"error": str(e)},
                ) from e
            else:
                raise ConnectionFailedError(
                    message=f"Failed to connect to BigQuery: {str(e)}",
                    details={"error": str(e)},
                ) from e

    async def disconnect(self) -> None:
        """Close BigQuery client."""
        if self._client:
            self._client.close()
            self._client = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test BigQuery connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            # Run a simple query to test connection
            query = "SELECT 1"
            query_job = self._client.query(query)
            query_job.result()

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version="Google BigQuery",
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

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        limit: int | None = None,
    ) -> QueryResult:
        """Execute a SQL query against BigQuery."""
        if not self._connected or not self._client:
            raise ConnectionFailedError(message="Not connected to BigQuery")

        start_time = time.time()
        try:
            from google.cloud import bigquery

            job_config = bigquery.QueryJobConfig()
            job_config.timeout_ms = timeout_seconds * 1000

            # Set default dataset if configured
            dataset = self._config.get("dataset")
            if dataset:
                project_id = self._config.get("project_id", "")
                job_config.default_dataset = f"{project_id}.{dataset}"

            query_job = self._client.query(sql, job_config=job_config)
            results = query_job.result(timeout=timeout_seconds)

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Get schema from result
            schema = results.schema
            if not schema:
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                )

            columns = [
                {"name": field.name, "data_type": self._map_bq_type(field.field_type)}
                for field in schema
            ]
            column_names = [field.name for field in schema]

            # Convert rows to dicts
            row_dicts = []
            for row in results:
                row_dict = {}
                for name in column_names:
                    value = row[name]
                    # Convert non-serializable types to strings
                    if hasattr(value, "isoformat"):
                        value = value.isoformat()
                    elif hasattr(value, "__iter__") and not isinstance(value, str | dict | list):
                        value = list(value)
                    row_dict[name] = value
                row_dicts.append(row_dict)

            # Apply limit if needed
            truncated = False
            if limit and len(row_dicts) > limit:
                row_dicts = row_dicts[:limit]
                truncated = True

            return QueryResult(
                columns=columns,
                rows=row_dicts,
                row_count=len(row_dicts),
                truncated=truncated,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            error_str = str(e).lower()
            if "syntax error" in error_str or "400" in error_str:
                raise QuerySyntaxError(
                    message=str(e),
                    query=sql[:200],
                ) from e
            elif "permission" in error_str or "403" in error_str:
                raise AccessDeniedError(
                    message=str(e),
                ) from e
            elif "timeout" in error_str or "deadline exceeded" in error_str:
                raise QueryTimeoutError(
                    message=str(e),
                    timeout_seconds=timeout_seconds,
                ) from e
            else:
                raise

    def _map_bq_type(self, bq_type: str) -> str:
        """Map BigQuery type to normalized type."""
        result: str = normalize_type(bq_type, SourceType.BIGQUERY).value
        return result

    async def _fetch_table_metadata(self) -> list[dict[str, Any]]:
        """Fetch table metadata from BigQuery."""
        project_id = self._config.get("project_id", "")
        dataset = self._config.get("dataset", "")

        if dataset:
            sql = f"""
                SELECT
                    '{project_id}' as table_catalog,
                    table_schema,
                    table_name,
                    table_type
                FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.TABLES`
                ORDER BY table_name
            """
        else:
            sql = f"""
                SELECT
                    '{project_id}' as table_catalog,
                    schema_name as table_schema,
                    '' as table_name,
                    'SCHEMA' as table_type
                FROM `{project_id}.INFORMATION_SCHEMA.SCHEMATA`
            """
        result = await self.execute_query(sql)
        return list(result.rows)

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get BigQuery schema."""
        if not self._connected or not self._client:
            raise ConnectionFailedError(message="Not connected to BigQuery")

        try:
            project_id = self._config.get("project_id", "")
            dataset = self._config.get("dataset", "")

            # If dataset specified, get tables from that dataset
            if dataset:
                return await self._get_dataset_schema(project_id, dataset, filter)
            else:
                # List all datasets and their tables
                return await self._get_project_schema(project_id, filter)

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch BigQuery schema: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def _get_dataset_schema(
        self,
        project_id: str,
        dataset: str,
        filter: SchemaFilter | None,
    ) -> SchemaResponse:
        """Get schema for a specific dataset."""
        # Build filter conditions
        conditions = []
        if filter:
            if filter.table_pattern:
                conditions.append(f"table_name LIKE '{filter.table_pattern}'")
            if not filter.include_views:
                conditions.append("table_type = 'BASE TABLE'")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        limit_clause = f"LIMIT {filter.max_tables}" if filter else "LIMIT 1000"

        # Get tables
        tables_sql = f"""
            SELECT
                table_schema,
                table_name,
                table_type
            FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.TABLES`
            {where_clause}
            ORDER BY table_name
            {limit_clause}
        """
        tables_result = await self.execute_query(tables_sql)

        # Get columns
        columns_sql = f"""
            SELECT
                table_schema,
                table_name,
                column_name,
                data_type,
                is_nullable,
                ordinal_position
            FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
            {where_clause}
            ORDER BY table_name, ordinal_position
        """
        columns_result = await self.execute_query(columns_sql)

        # Organize into schema response
        schema_map: dict[str, dict[str, dict[str, Any]]] = {}
        for row in tables_result.rows:
            schema_name = row["table_schema"]
            table_name = row["table_name"]
            table_type_raw = row["table_type"]

            table_type = "view" if "view" in table_type_raw.lower() else "table"

            if schema_name not in schema_map:
                schema_map[schema_name] = {}
            schema_map[schema_name][table_name] = {
                "name": table_name,
                "table_type": table_type,
                "native_type": table_type_raw,
                "native_path": f"{project_id}.{schema_name}.{table_name}",
                "columns": [],
            }

        # Add columns
        for row in columns_result.rows:
            schema_name = row["table_schema"]
            table_name = row["table_name"]
            if schema_name in schema_map and table_name in schema_map[schema_name]:
                col_data = {
                    "name": row["column_name"],
                    "data_type": normalize_type(row["data_type"], SourceType.BIGQUERY),
                    "native_type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "is_primary_key": False,
                    "is_partition_key": False,
                }
                schema_map[schema_name][table_name]["columns"].append(col_data)

        # Build catalog structure
        catalogs = [
            {
                "name": project_id,
                "schemas": [
                    {
                        "name": schema_name,
                        "tables": list(tables.values()),
                    }
                    for schema_name, tables in schema_map.items()
                ],
            }
        ]

        return self._build_schema_response(
            source_id=self._source_id or "bigquery",
            catalogs=catalogs,
        )

    async def _get_project_schema(
        self,
        project_id: str,
        filter: SchemaFilter | None,
    ) -> SchemaResponse:
        """Get schema for entire project (all datasets)."""
        # List all datasets
        datasets = list(self._client.list_datasets())

        schema_map: dict[str, dict[str, dict[str, Any]]] = {}

        for ds in datasets:
            dataset_id = ds.dataset_id

            # Skip if filter doesn't match
            if filter and filter.schema_pattern:
                if filter.schema_pattern not in dataset_id:
                    continue

            try:
                # Get tables for this dataset
                tables_sql = f"""
                    SELECT
                        table_schema,
                        table_name,
                        table_type
                    FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.TABLES`
                    ORDER BY table_name
                    LIMIT 100
                """
                tables_result = await self.execute_query(tables_sql)

                schema_map[dataset_id] = {}
                for row in tables_result.rows:
                    table_name = row["table_name"]
                    table_type_raw = row["table_type"]
                    table_type = "view" if "view" in table_type_raw.lower() else "table"

                    schema_map[dataset_id][table_name] = {
                        "name": table_name,
                        "table_type": table_type,
                        "native_type": table_type_raw,
                        "native_path": f"{project_id}.{dataset_id}.{table_name}",
                        "columns": [],
                    }

            except Exception:
                # Skip datasets we can't access
                continue

        # Build catalog structure
        catalogs = [
            {
                "name": project_id,
                "schemas": [
                    {
                        "name": schema_name,
                        "tables": list(tables.values()),
                    }
                    for schema_name, tables in schema_map.items()
                ],
            }
        ]

        return self._build_schema_response(
            source_id=self._source_id or "bigquery",
            catalogs=catalogs,
        )

    def _build_sample_query(self, table: str, n: int) -> str:
        """Build BigQuery-specific sampling query using TABLESAMPLE."""
        return f"SELECT * FROM {table} TABLESAMPLE SYSTEM (10 PERCENT) LIMIT {n}"
