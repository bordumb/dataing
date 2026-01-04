"""MongoDB adapter implementation.

This module provides a MongoDB adapter that implements the unified
data source interface with schema inference and document scanning.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from dataing.adapters.datasource.document.base import DocumentAdapter
from dataing.adapters.datasource.errors import (
    AuthenticationFailedError,
    ConnectionFailedError,
    ConnectionTimeoutError,
    SchemaFetchFailedError,
)
from dataing.adapters.datasource.registry import register_adapter
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

MONGODB_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="connection", label="Connection", collapsed_by_default=False),
    ],
    fields=[
        ConfigField(
            name="connection_string",
            label="Connection String",
            type="secret",
            required=True,
            group="connection",
            placeholder="mongodb+srv://user:pass@cluster.mongodb.net/db",
            description="Full MongoDB connection URI",
        ),
        ConfigField(
            name="database",
            label="Database",
            type="string",
            required=True,
            group="connection",
            description="Database to connect to",
        ),
    ],
)

MONGODB_CAPABILITIES = AdapterCapabilities(
    supports_sql=False,
    supports_sampling=True,
    supports_row_count=True,
    supports_column_stats=False,
    supports_preview=True,
    supports_write=False,
    query_language=QueryLanguage.MQL,
    max_concurrent_queries=5,
)


@register_adapter(
    source_type=SourceType.MONGODB,
    display_name="MongoDB",
    category=SourceCategory.DATABASE,
    icon="mongodb",
    description="Connect to MongoDB for document-oriented data querying",
    capabilities=MONGODB_CAPABILITIES,
    config_schema=MONGODB_CONFIG_SCHEMA,
)
class MongoDBAdapter(DocumentAdapter):
    """MongoDB database adapter.

    Provides schema inference and document scanning for MongoDB.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize MongoDB adapter.

        Args:
            config: Configuration dictionary with:
                - connection_string: MongoDB connection URI
                - database: Database name
        """
        super().__init__(config)
        self._client: Any = None
        self._db: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.MONGODB

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return MONGODB_CAPABILITIES

    async def connect(self) -> None:
        """Establish connection to MongoDB."""
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as e:
            raise ConnectionFailedError(
                message="motor is not installed. Install with: pip install motor",
                details={"error": str(e)},
            ) from e

        try:
            connection_string = self._config.get("connection_string", "")
            database = self._config.get("database", "")

            self._client = AsyncIOMotorClient(
                connection_string,
                serverSelectionTimeoutMS=30000,
            )
            self._db = self._client[database]

            # Test connection
            await self._client.admin.command("ping")
            self._connected = True
        except Exception as e:
            error_str = str(e).lower()
            if "authentication" in error_str:
                raise AuthenticationFailedError(
                    message="Authentication failed for MongoDB",
                    details={"error": str(e)},
                ) from e
            elif "timeout" in error_str or "timed out" in error_str:
                raise ConnectionTimeoutError(
                    message="Connection to MongoDB timed out",
                ) from e
            else:
                raise ConnectionFailedError(
                    message=f"Failed to connect to MongoDB: {str(e)}",
                    details={"error": str(e)},
                ) from e

    async def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test MongoDB connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            # Get server info
            info = await self._client.server_info()
            version = info.get("version", "Unknown")

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version=f"MongoDB {version}",
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
        """Scan documents from a collection."""
        if not self._connected or not self._db:
            raise ConnectionFailedError(message="Not connected to MongoDB")

        start_time = time.time()
        coll = self._db[collection]

        query_filter = filter or {}
        cursor = coll.find(query_filter).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)

        execution_time_ms = int((time.time() - start_time) * 1000)

        if not docs:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                execution_time_ms=execution_time_ms,
            )

        # Get all unique keys from documents
        all_keys: set[str] = set()
        for doc in docs:
            all_keys.update(doc.keys())

        columns = [{"name": key, "data_type": "json"} for key in sorted(all_keys)]

        # Convert documents to serializable dicts
        row_dicts = []
        for doc in docs:
            row = {}
            for key, value in doc.items():
                row[key] = self._serialize_value(value)
            row_dicts.append(row)

        return QueryResult(
            columns=columns,
            rows=row_dicts,
            row_count=len(row_dicts),
            execution_time_ms=execution_time_ms,
        )

    def _serialize_value(self, value: Any) -> Any:
        """Convert MongoDB values to JSON-serializable format."""
        from bson import ObjectId

        if isinstance(value, ObjectId):
            return str(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._serialize_value(v) for v in value]
        else:
            return value

    async def sample(
        self,
        collection: str,
        n: int = 100,
    ) -> QueryResult:
        """Get a random sample of documents."""
        if not self._connected or not self._db:
            raise ConnectionFailedError(message="Not connected to MongoDB")

        start_time = time.time()
        coll = self._db[collection]

        # Use $sample aggregation
        pipeline = [{"$sample": {"size": n}}]
        cursor = coll.aggregate(pipeline)
        docs = await cursor.to_list(length=n)

        execution_time_ms = int((time.time() - start_time) * 1000)

        if not docs:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                execution_time_ms=execution_time_ms,
            )

        # Get all unique keys
        all_keys: set[str] = set()
        for doc in docs:
            all_keys.update(doc.keys())

        columns = [{"name": key, "data_type": "json"} for key in sorted(all_keys)]

        row_dicts = []
        for doc in docs:
            row = {key: self._serialize_value(value) for key, value in doc.items()}
            row_dicts.append(row)

        return QueryResult(
            columns=columns,
            rows=row_dicts,
            row_count=len(row_dicts),
            execution_time_ms=execution_time_ms,
        )

    async def count_documents(
        self,
        collection: str,
        filter: dict[str, Any] | None = None,
    ) -> int:
        """Count documents in a collection."""
        if not self._connected or not self._db:
            raise ConnectionFailedError(message="Not connected to MongoDB")

        coll = self._db[collection]
        query_filter = filter or {}
        count: int = await coll.count_documents(query_filter)
        return count

    async def aggregate(
        self,
        collection: str,
        pipeline: list[dict[str, Any]],
    ) -> QueryResult:
        """Execute an aggregation pipeline."""
        if not self._connected or not self._db:
            raise ConnectionFailedError(message="Not connected to MongoDB")

        start_time = time.time()
        coll = self._db[collection]

        cursor = coll.aggregate(pipeline)
        docs = await cursor.to_list(length=1000)

        execution_time_ms = int((time.time() - start_time) * 1000)

        if not docs:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                execution_time_ms=execution_time_ms,
            )

        # Get all unique keys
        all_keys: set[str] = set()
        for doc in docs:
            all_keys.update(doc.keys())

        columns = [{"name": key, "data_type": "json"} for key in sorted(all_keys)]

        row_dicts = []
        for doc in docs:
            row = {key: self._serialize_value(value) for key, value in doc.items()}
            row_dicts.append(row)

        return QueryResult(
            columns=columns,
            rows=row_dicts,
            row_count=len(row_dicts),
            execution_time_ms=execution_time_ms,
        )

    async def infer_schema(
        self,
        collection: str,
        sample_size: int = 100,
    ) -> dict[str, Any]:
        """Infer schema from document samples."""
        if not self._connected or not self._db:
            raise ConnectionFailedError(message="Not connected to MongoDB")

        sample_result = await self.sample(collection, sample_size)

        # Track field types across all documents
        field_types: dict[str, set[str]] = {}

        for doc in sample_result.rows:
            for key, value in doc.items():
                if key not in field_types:
                    field_types[key] = set()
                field_types[key].add(self._infer_type(value))

        # Build schema
        schema: dict[str, Any] = {
            "collection": collection,
            "fields": {},
        }

        for field, types in field_types.items():
            # If multiple types, use the most common or 'mixed'
            if len(types) == 1:
                schema["fields"][field] = list(types)[0]
            else:
                schema["fields"][field] = "mixed"

        return schema

    def _infer_type(self, value: Any) -> str:
        """Infer the type of a value."""
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, list):
            return "array"
        elif isinstance(value, dict):
            return "object"
        else:
            return "unknown"

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get MongoDB schema (collections with inferred types)."""
        if not self._connected or not self._db:
            raise ConnectionFailedError(message="Not connected to MongoDB")

        try:
            # List collections
            collections = await self._db.list_collection_names()

            # Apply filter if provided
            if filter and filter.table_pattern:
                import fnmatch

                pattern = filter.table_pattern.replace("%", "*")
                collections = [c for c in collections if fnmatch.fnmatch(c, pattern)]

            # Limit collections
            max_tables = filter.max_tables if filter else 1000
            collections = collections[:max_tables]

            # Build tables with inferred schemas
            tables = []
            for coll_name in collections:
                # Skip system collections
                if coll_name.startswith("system."):
                    continue

                try:
                    # Sample documents to infer schema
                    schema_info = await self.infer_schema(coll_name, sample_size=50)

                    # Get document count
                    count = await self.count_documents(coll_name)

                    # Build columns from inferred schema
                    columns = []
                    for field_name, field_type in schema_info.get("fields", {}).items():
                        normalized_type = normalize_type(field_type, SourceType.MONGODB)
                        columns.append(
                            {
                                "name": field_name,
                                "data_type": normalized_type,
                                "native_type": field_type,
                                "nullable": True,
                                "is_primary_key": field_name == "_id",
                                "is_partition_key": False,
                            }
                        )

                    tables.append(
                        {
                            "name": coll_name,
                            "table_type": "collection",
                            "native_type": "COLLECTION",
                            "native_path": f"{self._config.get('database', 'db')}.{coll_name}",
                            "columns": columns,
                            "row_count": count,
                        }
                    )
                except Exception:
                    # If we can't infer schema, add empty table
                    tables.append(
                        {
                            "name": coll_name,
                            "table_type": "collection",
                            "native_type": "COLLECTION",
                            "native_path": f"{self._config.get('database', 'db')}.{coll_name}",
                            "columns": [],
                        }
                    )

            # Build catalog structure
            catalogs = [
                {
                    "name": "default",
                    "schemas": [
                        {
                            "name": self._config.get("database", "default"),
                            "tables": tables,
                        }
                    ],
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "mongodb",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch MongoDB schema: {str(e)}",
                details={"error": str(e)},
            ) from e
