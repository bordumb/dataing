"""Type normalization mappings for all data sources.

This module provides mappings from native data types to normalized types,
ensuring consistent type representation across all source types.
"""

from __future__ import annotations

import re

from dataing.adapters.datasource.types import NormalizedType, SourceType

# PostgreSQL type mappings
POSTGRESQL_TYPE_MAP: dict[str, NormalizedType] = {
    # String types
    "varchar": NormalizedType.STRING,
    "character varying": NormalizedType.STRING,
    "text": NormalizedType.STRING,
    "char": NormalizedType.STRING,
    "character": NormalizedType.STRING,
    "name": NormalizedType.STRING,
    "uuid": NormalizedType.STRING,
    "citext": NormalizedType.STRING,
    # Integer types
    "smallint": NormalizedType.INTEGER,
    "integer": NormalizedType.INTEGER,
    "int": NormalizedType.INTEGER,
    "int2": NormalizedType.INTEGER,
    "int4": NormalizedType.INTEGER,
    "bigint": NormalizedType.INTEGER,
    "int8": NormalizedType.INTEGER,
    "serial": NormalizedType.INTEGER,
    "bigserial": NormalizedType.INTEGER,
    "smallserial": NormalizedType.INTEGER,
    # Float types
    "real": NormalizedType.FLOAT,
    "float4": NormalizedType.FLOAT,
    "double precision": NormalizedType.FLOAT,
    "float8": NormalizedType.FLOAT,
    # Decimal types
    "numeric": NormalizedType.DECIMAL,
    "decimal": NormalizedType.DECIMAL,
    "money": NormalizedType.DECIMAL,
    # Boolean
    "boolean": NormalizedType.BOOLEAN,
    "bool": NormalizedType.BOOLEAN,
    # Date/Time types
    "date": NormalizedType.DATE,
    "time": NormalizedType.TIME,
    "time without time zone": NormalizedType.TIME,
    "time with time zone": NormalizedType.TIME,
    "timestamp": NormalizedType.TIMESTAMP,
    "timestamp without time zone": NormalizedType.TIMESTAMP,
    "timestamp with time zone": NormalizedType.TIMESTAMP,
    "timestamptz": NormalizedType.TIMESTAMP,
    "interval": NormalizedType.STRING,
    # Binary
    "bytea": NormalizedType.BINARY,
    # JSON types
    "json": NormalizedType.JSON,
    "jsonb": NormalizedType.JSON,
    # Array type (handled specially)
    "array": NormalizedType.ARRAY,
    # Geometric types (map to string for now)
    "point": NormalizedType.STRING,
    "line": NormalizedType.STRING,
    "lseg": NormalizedType.STRING,
    "box": NormalizedType.STRING,
    "path": NormalizedType.STRING,
    "polygon": NormalizedType.STRING,
    "circle": NormalizedType.STRING,
    # Network types
    "inet": NormalizedType.STRING,
    "cidr": NormalizedType.STRING,
    "macaddr": NormalizedType.STRING,
    "macaddr8": NormalizedType.STRING,
    # Bit strings
    "bit": NormalizedType.STRING,
    "bit varying": NormalizedType.STRING,
    # Other
    "xml": NormalizedType.STRING,
    "oid": NormalizedType.INTEGER,
}

# MySQL type mappings
MYSQL_TYPE_MAP: dict[str, NormalizedType] = {
    # String types
    "varchar": NormalizedType.STRING,
    "char": NormalizedType.STRING,
    "text": NormalizedType.STRING,
    "tinytext": NormalizedType.STRING,
    "mediumtext": NormalizedType.STRING,
    "longtext": NormalizedType.STRING,
    "enum": NormalizedType.STRING,
    "set": NormalizedType.STRING,
    # Integer types
    "tinyint": NormalizedType.INTEGER,
    "smallint": NormalizedType.INTEGER,
    "mediumint": NormalizedType.INTEGER,
    "int": NormalizedType.INTEGER,
    "integer": NormalizedType.INTEGER,
    "bigint": NormalizedType.INTEGER,
    # Float types
    "float": NormalizedType.FLOAT,
    "double": NormalizedType.FLOAT,
    "double precision": NormalizedType.FLOAT,
    # Decimal types
    "decimal": NormalizedType.DECIMAL,
    "numeric": NormalizedType.DECIMAL,
    # Boolean (MySQL uses TINYINT(1))
    "bit": NormalizedType.BOOLEAN,
    # Date/Time types
    "date": NormalizedType.DATE,
    "time": NormalizedType.TIME,
    "datetime": NormalizedType.DATETIME,
    "timestamp": NormalizedType.TIMESTAMP,
    "year": NormalizedType.INTEGER,
    # Binary types
    "binary": NormalizedType.BINARY,
    "varbinary": NormalizedType.BINARY,
    "tinyblob": NormalizedType.BINARY,
    "blob": NormalizedType.BINARY,
    "mediumblob": NormalizedType.BINARY,
    "longblob": NormalizedType.BINARY,
    # JSON
    "json": NormalizedType.JSON,
    # Spatial types
    "geometry": NormalizedType.STRING,
    "point": NormalizedType.STRING,
    "linestring": NormalizedType.STRING,
    "polygon": NormalizedType.STRING,
}

# Snowflake type mappings
SNOWFLAKE_TYPE_MAP: dict[str, NormalizedType] = {
    # String types
    "varchar": NormalizedType.STRING,
    "char": NormalizedType.STRING,
    "character": NormalizedType.STRING,
    "string": NormalizedType.STRING,
    "text": NormalizedType.STRING,
    # Integer types
    "number": NormalizedType.DECIMAL,  # NUMBER can be decimal
    "int": NormalizedType.INTEGER,
    "integer": NormalizedType.INTEGER,
    "bigint": NormalizedType.INTEGER,
    "smallint": NormalizedType.INTEGER,
    "tinyint": NormalizedType.INTEGER,
    "byteint": NormalizedType.INTEGER,
    # Float types
    "float": NormalizedType.FLOAT,
    "float4": NormalizedType.FLOAT,
    "float8": NormalizedType.FLOAT,
    "double": NormalizedType.FLOAT,
    "double precision": NormalizedType.FLOAT,
    "real": NormalizedType.FLOAT,
    # Decimal types
    "decimal": NormalizedType.DECIMAL,
    "numeric": NormalizedType.DECIMAL,
    # Boolean
    "boolean": NormalizedType.BOOLEAN,
    # Date/Time types
    "date": NormalizedType.DATE,
    "time": NormalizedType.TIME,
    "datetime": NormalizedType.DATETIME,
    "timestamp": NormalizedType.TIMESTAMP,
    "timestamp_ntz": NormalizedType.TIMESTAMP,
    "timestamp_ltz": NormalizedType.TIMESTAMP,
    "timestamp_tz": NormalizedType.TIMESTAMP,
    # Binary
    "binary": NormalizedType.BINARY,
    "varbinary": NormalizedType.BINARY,
    # Semi-structured types
    "variant": NormalizedType.JSON,
    "object": NormalizedType.MAP,
    "array": NormalizedType.ARRAY,
    # Geography
    "geography": NormalizedType.STRING,
    "geometry": NormalizedType.STRING,
}

# BigQuery type mappings
BIGQUERY_TYPE_MAP: dict[str, NormalizedType] = {
    # String types
    "string": NormalizedType.STRING,
    "bytes": NormalizedType.BINARY,
    # Integer types
    "int64": NormalizedType.INTEGER,
    "int": NormalizedType.INTEGER,
    "smallint": NormalizedType.INTEGER,
    "integer": NormalizedType.INTEGER,
    "bigint": NormalizedType.INTEGER,
    "tinyint": NormalizedType.INTEGER,
    "byteint": NormalizedType.INTEGER,
    # Float types
    "float64": NormalizedType.FLOAT,
    "float": NormalizedType.FLOAT,
    # Decimal types
    "numeric": NormalizedType.DECIMAL,
    "bignumeric": NormalizedType.DECIMAL,
    "decimal": NormalizedType.DECIMAL,
    "bigdecimal": NormalizedType.DECIMAL,
    # Boolean
    "bool": NormalizedType.BOOLEAN,
    "boolean": NormalizedType.BOOLEAN,
    # Date/Time types
    "date": NormalizedType.DATE,
    "time": NormalizedType.TIME,
    "datetime": NormalizedType.DATETIME,
    "timestamp": NormalizedType.TIMESTAMP,
    # Complex types
    "struct": NormalizedType.STRUCT,
    "record": NormalizedType.STRUCT,
    "array": NormalizedType.ARRAY,
    "json": NormalizedType.JSON,
    # Geography
    "geography": NormalizedType.STRING,
    "interval": NormalizedType.STRING,
}

# Trino type mappings (similar to Presto)
TRINO_TYPE_MAP: dict[str, NormalizedType] = {
    # String types
    "varchar": NormalizedType.STRING,
    "char": NormalizedType.STRING,
    "varbinary": NormalizedType.BINARY,
    "json": NormalizedType.JSON,
    # Integer types
    "tinyint": NormalizedType.INTEGER,
    "smallint": NormalizedType.INTEGER,
    "integer": NormalizedType.INTEGER,
    "bigint": NormalizedType.INTEGER,
    # Float types
    "real": NormalizedType.FLOAT,
    "double": NormalizedType.FLOAT,
    # Decimal types
    "decimal": NormalizedType.DECIMAL,
    # Boolean
    "boolean": NormalizedType.BOOLEAN,
    # Date/Time types
    "date": NormalizedType.DATE,
    "time": NormalizedType.TIME,
    "time with time zone": NormalizedType.TIME,
    "timestamp": NormalizedType.TIMESTAMP,
    "timestamp with time zone": NormalizedType.TIMESTAMP,
    "interval year to month": NormalizedType.STRING,
    "interval day to second": NormalizedType.STRING,
    # Complex types
    "array": NormalizedType.ARRAY,
    "map": NormalizedType.MAP,
    "row": NormalizedType.STRUCT,
    # Other
    "uuid": NormalizedType.STRING,
    "ipaddress": NormalizedType.STRING,
}

# DuckDB type mappings
DUCKDB_TYPE_MAP: dict[str, NormalizedType] = {
    # String types
    "varchar": NormalizedType.STRING,
    "char": NormalizedType.STRING,
    "bpchar": NormalizedType.STRING,
    "text": NormalizedType.STRING,
    "string": NormalizedType.STRING,
    "uuid": NormalizedType.STRING,
    # Integer types
    "tinyint": NormalizedType.INTEGER,
    "smallint": NormalizedType.INTEGER,
    "integer": NormalizedType.INTEGER,
    "int": NormalizedType.INTEGER,
    "bigint": NormalizedType.INTEGER,
    "hugeint": NormalizedType.INTEGER,
    "utinyint": NormalizedType.INTEGER,
    "usmallint": NormalizedType.INTEGER,
    "uinteger": NormalizedType.INTEGER,
    "ubigint": NormalizedType.INTEGER,
    # Float types
    "real": NormalizedType.FLOAT,
    "float": NormalizedType.FLOAT,
    "double": NormalizedType.FLOAT,
    # Decimal types
    "decimal": NormalizedType.DECIMAL,
    "numeric": NormalizedType.DECIMAL,
    # Boolean
    "boolean": NormalizedType.BOOLEAN,
    "bool": NormalizedType.BOOLEAN,
    # Date/Time types
    "date": NormalizedType.DATE,
    "time": NormalizedType.TIME,
    "timestamp": NormalizedType.TIMESTAMP,
    "timestamptz": NormalizedType.TIMESTAMP,
    "timestamp with time zone": NormalizedType.TIMESTAMP,
    "interval": NormalizedType.STRING,
    # Binary
    "blob": NormalizedType.BINARY,
    "bytea": NormalizedType.BINARY,
    # Complex types
    "list": NormalizedType.ARRAY,
    "struct": NormalizedType.STRUCT,
    "map": NormalizedType.MAP,
    "json": NormalizedType.JSON,
}

# MongoDB type mappings
MONGODB_TYPE_MAP: dict[str, NormalizedType] = {
    "string": NormalizedType.STRING,
    "int": NormalizedType.INTEGER,
    "int32": NormalizedType.INTEGER,
    "long": NormalizedType.INTEGER,
    "int64": NormalizedType.INTEGER,
    "double": NormalizedType.FLOAT,
    "decimal": NormalizedType.DECIMAL,
    "decimal128": NormalizedType.DECIMAL,
    "bool": NormalizedType.BOOLEAN,
    "boolean": NormalizedType.BOOLEAN,
    "date": NormalizedType.TIMESTAMP,
    "timestamp": NormalizedType.TIMESTAMP,
    "objectid": NormalizedType.STRING,
    "object": NormalizedType.JSON,
    "array": NormalizedType.ARRAY,
    "bindata": NormalizedType.BINARY,
    "null": NormalizedType.UNKNOWN,
    "regex": NormalizedType.STRING,
    "javascript": NormalizedType.STRING,
    "symbol": NormalizedType.STRING,
    "minkey": NormalizedType.STRING,
    "maxkey": NormalizedType.STRING,
}

# DynamoDB type mappings
DYNAMODB_TYPE_MAP: dict[str, NormalizedType] = {
    "s": NormalizedType.STRING,  # String
    "n": NormalizedType.DECIMAL,  # Number
    "b": NormalizedType.BINARY,  # Binary
    "bool": NormalizedType.BOOLEAN,
    "null": NormalizedType.UNKNOWN,
    "m": NormalizedType.MAP,  # Map
    "l": NormalizedType.ARRAY,  # List
    "ss": NormalizedType.ARRAY,  # String Set
    "ns": NormalizedType.ARRAY,  # Number Set
    "bs": NormalizedType.ARRAY,  # Binary Set
}

# Salesforce type mappings
SALESFORCE_TYPE_MAP: dict[str, NormalizedType] = {
    "id": NormalizedType.STRING,
    "string": NormalizedType.STRING,
    "textarea": NormalizedType.STRING,
    "phone": NormalizedType.STRING,
    "email": NormalizedType.STRING,
    "url": NormalizedType.STRING,
    "picklist": NormalizedType.STRING,
    "multipicklist": NormalizedType.STRING,
    "combobox": NormalizedType.STRING,
    "reference": NormalizedType.STRING,
    "int": NormalizedType.INTEGER,
    "double": NormalizedType.DECIMAL,
    "currency": NormalizedType.DECIMAL,
    "percent": NormalizedType.DECIMAL,
    "boolean": NormalizedType.BOOLEAN,
    "date": NormalizedType.DATE,
    "datetime": NormalizedType.TIMESTAMP,
    "time": NormalizedType.TIME,
    "base64": NormalizedType.BINARY,
    "location": NormalizedType.JSON,
    "address": NormalizedType.JSON,
    "encryptedstring": NormalizedType.STRING,
}

# HubSpot type mappings
HUBSPOT_TYPE_MAP: dict[str, NormalizedType] = {
    "string": NormalizedType.STRING,
    "number": NormalizedType.DECIMAL,
    "date": NormalizedType.DATE,
    "datetime": NormalizedType.TIMESTAMP,
    "enumeration": NormalizedType.STRING,
    "bool": NormalizedType.BOOLEAN,
    "phone_number": NormalizedType.STRING,
}

# Parquet/Arrow type mappings (for file systems)
PARQUET_TYPE_MAP: dict[str, NormalizedType] = {
    "utf8": NormalizedType.STRING,
    "string": NormalizedType.STRING,
    "large_string": NormalizedType.STRING,
    "int8": NormalizedType.INTEGER,
    "int16": NormalizedType.INTEGER,
    "int32": NormalizedType.INTEGER,
    "int64": NormalizedType.INTEGER,
    "uint8": NormalizedType.INTEGER,
    "uint16": NormalizedType.INTEGER,
    "uint32": NormalizedType.INTEGER,
    "uint64": NormalizedType.INTEGER,
    "float": NormalizedType.FLOAT,
    "float16": NormalizedType.FLOAT,
    "float32": NormalizedType.FLOAT,
    "double": NormalizedType.FLOAT,
    "float64": NormalizedType.FLOAT,
    "decimal": NormalizedType.DECIMAL,
    "decimal128": NormalizedType.DECIMAL,
    "decimal256": NormalizedType.DECIMAL,
    "bool": NormalizedType.BOOLEAN,
    "boolean": NormalizedType.BOOLEAN,
    "date": NormalizedType.DATE,
    "date32": NormalizedType.DATE,
    "date64": NormalizedType.DATE,
    "time": NormalizedType.TIME,
    "time32": NormalizedType.TIME,
    "time64": NormalizedType.TIME,
    "timestamp": NormalizedType.TIMESTAMP,
    "binary": NormalizedType.BINARY,
    "large_binary": NormalizedType.BINARY,
    "fixed_size_binary": NormalizedType.BINARY,
    "list": NormalizedType.ARRAY,
    "large_list": NormalizedType.ARRAY,
    "fixed_size_list": NormalizedType.ARRAY,
    "map": NormalizedType.MAP,
    "struct": NormalizedType.STRUCT,
    "dictionary": NormalizedType.STRING,
    "null": NormalizedType.UNKNOWN,
}

# Master mapping from source type to type map
SOURCE_TYPE_MAPS: dict[SourceType, dict[str, NormalizedType]] = {
    SourceType.POSTGRESQL: POSTGRESQL_TYPE_MAP,
    SourceType.MYSQL: MYSQL_TYPE_MAP,
    SourceType.SNOWFLAKE: SNOWFLAKE_TYPE_MAP,
    SourceType.BIGQUERY: BIGQUERY_TYPE_MAP,
    SourceType.TRINO: TRINO_TYPE_MAP,
    SourceType.REDSHIFT: POSTGRESQL_TYPE_MAP,  # Redshift is PostgreSQL-based
    SourceType.DUCKDB: DUCKDB_TYPE_MAP,
    SourceType.MONGODB: MONGODB_TYPE_MAP,
    SourceType.DYNAMODB: DYNAMODB_TYPE_MAP,
    SourceType.CASSANDRA: POSTGRESQL_TYPE_MAP,  # Similar enough
    SourceType.SALESFORCE: SALESFORCE_TYPE_MAP,
    SourceType.HUBSPOT: HUBSPOT_TYPE_MAP,
    SourceType.STRIPE: HUBSPOT_TYPE_MAP,  # Similar type system
    SourceType.S3: PARQUET_TYPE_MAP,
    SourceType.GCS: PARQUET_TYPE_MAP,
    SourceType.HDFS: PARQUET_TYPE_MAP,
    SourceType.LOCAL_FILE: PARQUET_TYPE_MAP,
}


def normalize_type(
    native_type: str,
    source_type: SourceType,
) -> NormalizedType:
    """Normalize a native type to the standard type system.

    Args:
        native_type: The native type string from the data source.
        source_type: The source type to use for mapping.

    Returns:
        Normalized type enum value.
    """
    if not native_type:
        return NormalizedType.UNKNOWN

    # Get the type map for this source
    type_map = SOURCE_TYPE_MAPS.get(source_type, {})

    # Clean up the native type
    clean_type = native_type.lower().strip()

    # Handle array types (e.g., "integer[]", "ARRAY<string>")
    if "[]" in clean_type or clean_type.startswith("array"):
        return NormalizedType.ARRAY

    # Handle parameterized types (e.g., "varchar(255)", "decimal(10,2)")
    base_type = re.sub(r"\(.*\)", "", clean_type).strip()

    # Try exact match first
    if base_type in type_map:
        return type_map[base_type]

    # Try partial match
    for key, value in type_map.items():
        if key in base_type or base_type in key:
            return value

    return NormalizedType.UNKNOWN


def get_type_map(source_type: SourceType) -> dict[str, NormalizedType]:
    """Get the type mapping dictionary for a source type.

    Args:
        source_type: The source type.

    Returns:
        Dictionary mapping native types to normalized types.
    """
    return SOURCE_TYPE_MAPS.get(source_type, {})
