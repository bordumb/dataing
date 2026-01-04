"""Unified data source adapter layer.

This module provides a pluggable adapter architecture that normalizes
heterogeneous data sources (SQL databases, NoSQL stores, APIs, file systems)
into a unified interface.

Core Principle: All sources become "tables with columns" from the frontend's perspective.
"""

from dataing.adapters.datasource.api.hubspot import HubSpotAdapter

# API adapters
from dataing.adapters.datasource.api.salesforce import SalesforceAdapter
from dataing.adapters.datasource.api.stripe import StripeAdapter
from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.document.cassandra import CassandraAdapter
from dataing.adapters.datasource.document.dynamodb import DynamoDBAdapter

# Document/NoSQL adapters
from dataing.adapters.datasource.document.mongodb import MongoDBAdapter
from dataing.adapters.datasource.errors import (
    AccessDeniedError,
    AdapterError,
    AuthenticationFailedError,
    ConnectionFailedError,
    ConnectionTimeoutError,
    QuerySyntaxError,
    QueryTimeoutError,
    RateLimitedError,
    SchemaFetchFailedError,
    TableNotFoundError,
)
from dataing.adapters.datasource.filesystem.gcs import GCSAdapter
from dataing.adapters.datasource.filesystem.hdfs import HDFSAdapter
from dataing.adapters.datasource.filesystem.local import LocalFileAdapter

# Filesystem adapters
from dataing.adapters.datasource.filesystem.s3 import S3Adapter
from dataing.adapters.datasource.registry import AdapterRegistry, get_registry
from dataing.adapters.datasource.sql.bigquery import BigQueryAdapter
from dataing.adapters.datasource.sql.duckdb import DuckDBAdapter
from dataing.adapters.datasource.sql.mysql import MySQLAdapter

# Import adapters to trigger registration via decorators
# SQL adapters
from dataing.adapters.datasource.sql.postgres import PostgresAdapter
from dataing.adapters.datasource.sql.redshift import RedshiftAdapter
from dataing.adapters.datasource.sql.snowflake import SnowflakeAdapter
from dataing.adapters.datasource.sql.trino import TrinoAdapter
from dataing.adapters.datasource.type_mapping import normalize_type
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    Catalog,
    Column,
    ColumnStats,
    ConfigField,
    ConfigSchema,
    ConnectionTestResult,
    FieldGroup,
    NormalizedType,
    QueryResult,
    Schema,
    SchemaFilter,
    SchemaResponse,
    SourceCategory,
    SourceType,
    SourceTypeDefinition,
    Table,
)

__all__ = [
    # Base classes
    "BaseAdapter",
    "AdapterRegistry",
    "get_registry",
    # SQL Adapters
    "PostgresAdapter",
    "DuckDBAdapter",
    "MySQLAdapter",
    "TrinoAdapter",
    "SnowflakeAdapter",
    "BigQueryAdapter",
    "RedshiftAdapter",
    # Document/NoSQL Adapters
    "MongoDBAdapter",
    "DynamoDBAdapter",
    "CassandraAdapter",
    # API Adapters
    "SalesforceAdapter",
    "HubSpotAdapter",
    "StripeAdapter",
    # Filesystem Adapters
    "S3Adapter",
    "GCSAdapter",
    "HDFSAdapter",
    "LocalFileAdapter",
    # Types
    "AdapterCapabilities",
    "Catalog",
    "Column",
    "ColumnStats",
    "ConfigField",
    "ConfigSchema",
    "ConnectionTestResult",
    "FieldGroup",
    "NormalizedType",
    "QueryResult",
    "Schema",
    "SchemaFilter",
    "SchemaResponse",
    "SourceCategory",
    "SourceType",
    "SourceTypeDefinition",
    "Table",
    # Functions
    "normalize_type",
    # Errors
    "AdapterError",
    "ConnectionFailedError",
    "ConnectionTimeoutError",
    "AuthenticationFailedError",
    "AccessDeniedError",
    "QuerySyntaxError",
    "QueryTimeoutError",
    "RateLimitedError",
    "SchemaFetchFailedError",
    "TableNotFoundError",
]
