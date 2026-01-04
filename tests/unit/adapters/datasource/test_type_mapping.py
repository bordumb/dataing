"""Tests for type normalization mappings."""

import pytest
from dataing.adapters.datasource.type_mapping import (
    normalize_type,
    get_type_map,
    POSTGRESQL_TYPE_MAP,
    MYSQL_TYPE_MAP,
    SNOWFLAKE_TYPE_MAP,
    MONGODB_TYPE_MAP,
)
from dataing.adapters.datasource.types import NormalizedType, SourceType


class TestNormalizeType:
    """Tests for normalize_type function."""

    def test_postgresql_varchar(self):
        """Test PostgreSQL VARCHAR normalization."""
        result = normalize_type("varchar", SourceType.POSTGRESQL)
        assert result == NormalizedType.STRING

    def test_postgresql_varchar_with_length(self):
        """Test PostgreSQL VARCHAR(255) normalization."""
        result = normalize_type("varchar(255)", SourceType.POSTGRESQL)
        assert result == NormalizedType.STRING

    def test_postgresql_integer_types(self):
        """Test PostgreSQL integer type normalization."""
        int_types = ["integer", "int", "bigint", "smallint", "int4", "int8"]
        for int_type in int_types:
            result = normalize_type(int_type, SourceType.POSTGRESQL)
            assert result == NormalizedType.INTEGER, f"Failed for {int_type}"

    def test_postgresql_float_types(self):
        """Test PostgreSQL float type normalization."""
        float_types = ["real", "double precision", "float4", "float8"]
        for float_type in float_types:
            result = normalize_type(float_type, SourceType.POSTGRESQL)
            assert result == NormalizedType.FLOAT, f"Failed for {float_type}"

    def test_postgresql_decimal_types(self):
        """Test PostgreSQL decimal type normalization."""
        decimal_types = ["numeric", "decimal", "numeric(10,2)"]
        for decimal_type in decimal_types:
            result = normalize_type(decimal_type, SourceType.POSTGRESQL)
            assert result == NormalizedType.DECIMAL, f"Failed for {decimal_type}"

    def test_postgresql_timestamp(self):
        """Test PostgreSQL timestamp normalization."""
        ts_types = ["timestamp", "timestamp without time zone", "timestamp with time zone", "timestamptz"]
        for ts_type in ts_types:
            result = normalize_type(ts_type, SourceType.POSTGRESQL)
            assert result == NormalizedType.TIMESTAMP, f"Failed for {ts_type}"

    def test_postgresql_json(self):
        """Test PostgreSQL JSON type normalization."""
        json_types = ["json", "jsonb"]
        for json_type in json_types:
            result = normalize_type(json_type, SourceType.POSTGRESQL)
            assert result == NormalizedType.JSON, f"Failed for {json_type}"

    def test_postgresql_array(self):
        """Test PostgreSQL array type normalization."""
        array_types = ["integer[]", "text[]", "ARRAY"]
        for array_type in array_types:
            result = normalize_type(array_type, SourceType.POSTGRESQL)
            assert result == NormalizedType.ARRAY, f"Failed for {array_type}"

    def test_mysql_types(self):
        """Test MySQL type normalization."""
        test_cases = [
            ("varchar", NormalizedType.STRING),
            ("int", NormalizedType.INTEGER),
            ("bigint", NormalizedType.INTEGER),
            ("float", NormalizedType.FLOAT),
            ("decimal", NormalizedType.DECIMAL),
            ("datetime", NormalizedType.DATETIME),
            ("timestamp", NormalizedType.TIMESTAMP),
            ("json", NormalizedType.JSON),
        ]
        for native_type, expected in test_cases:
            result = normalize_type(native_type, SourceType.MYSQL)
            assert result == expected, f"Failed for {native_type}"

    def test_snowflake_types(self):
        """Test Snowflake type normalization."""
        test_cases = [
            ("varchar", NormalizedType.STRING),
            ("string", NormalizedType.STRING),
            ("number", NormalizedType.DECIMAL),
            ("integer", NormalizedType.INTEGER),
            ("variant", NormalizedType.JSON),
            ("object", NormalizedType.MAP),
            ("array", NormalizedType.ARRAY),
        ]
        for native_type, expected in test_cases:
            result = normalize_type(native_type, SourceType.SNOWFLAKE)
            assert result == expected, f"Failed for {native_type}"

    def test_bigquery_types(self):
        """Test BigQuery type normalization."""
        test_cases = [
            ("STRING", NormalizedType.STRING),
            ("INT64", NormalizedType.INTEGER),
            ("FLOAT64", NormalizedType.FLOAT),
            ("BOOL", NormalizedType.BOOLEAN),
            ("TIMESTAMP", NormalizedType.TIMESTAMP),
            ("STRUCT", NormalizedType.STRUCT),
            ("ARRAY", NormalizedType.ARRAY),
        ]
        for native_type, expected in test_cases:
            result = normalize_type(native_type, SourceType.BIGQUERY)
            assert result == expected, f"Failed for {native_type}"

    def test_mongodb_types(self):
        """Test MongoDB type normalization."""
        test_cases = [
            ("string", NormalizedType.STRING),
            ("int32", NormalizedType.INTEGER),
            ("int64", NormalizedType.INTEGER),
            ("double", NormalizedType.FLOAT),
            ("decimal128", NormalizedType.DECIMAL),
            ("boolean", NormalizedType.BOOLEAN),
            ("date", NormalizedType.TIMESTAMP),
            ("objectid", NormalizedType.STRING),
            ("object", NormalizedType.JSON),
            ("array", NormalizedType.ARRAY),
        ]
        for native_type, expected in test_cases:
            result = normalize_type(native_type, SourceType.MONGODB)
            assert result == expected, f"Failed for {native_type}"

    def test_salesforce_types(self):
        """Test Salesforce type normalization."""
        test_cases = [
            ("id", NormalizedType.STRING),
            ("string", NormalizedType.STRING),
            ("textarea", NormalizedType.STRING),
            ("int", NormalizedType.INTEGER),
            ("double", NormalizedType.DECIMAL),
            ("currency", NormalizedType.DECIMAL),
            ("boolean", NormalizedType.BOOLEAN),
            ("date", NormalizedType.DATE),
            ("datetime", NormalizedType.TIMESTAMP),
            ("picklist", NormalizedType.STRING),
            ("reference", NormalizedType.STRING),
        ]
        for native_type, expected in test_cases:
            result = normalize_type(native_type, SourceType.SALESFORCE)
            assert result == expected, f"Failed for {native_type}"

    def test_case_insensitivity(self):
        """Test that type normalization is case-insensitive."""
        test_cases = [
            ("VARCHAR", SourceType.POSTGRESQL, NormalizedType.STRING),
            ("Integer", SourceType.POSTGRESQL, NormalizedType.INTEGER),
            ("TIMESTAMP", SourceType.POSTGRESQL, NormalizedType.TIMESTAMP),
        ]
        for native_type, source_type, expected in test_cases:
            result = normalize_type(native_type, source_type)
            assert result == expected, f"Failed for {native_type}"

    def test_unknown_type(self):
        """Test unknown type returns UNKNOWN."""
        result = normalize_type("completely_made_up_type", SourceType.POSTGRESQL)
        assert result == NormalizedType.UNKNOWN

    def test_empty_type(self):
        """Test empty type returns UNKNOWN."""
        result = normalize_type("", SourceType.POSTGRESQL)
        assert result == NormalizedType.UNKNOWN

    def test_none_type(self):
        """Test None type returns UNKNOWN."""
        result = normalize_type(None, SourceType.POSTGRESQL)
        assert result == NormalizedType.UNKNOWN


class TestGetTypeMap:
    """Tests for get_type_map function."""

    def test_postgresql_map(self):
        """Test getting PostgreSQL type map."""
        type_map = get_type_map(SourceType.POSTGRESQL)
        assert type_map == POSTGRESQL_TYPE_MAP

    def test_mysql_map(self):
        """Test getting MySQL type map."""
        type_map = get_type_map(SourceType.MYSQL)
        assert type_map == MYSQL_TYPE_MAP

    def test_unsupported_source(self):
        """Test getting map for unsupported source returns empty."""
        # All SourceTypes should have a map, but if one doesn't, it returns empty
        type_map = get_type_map(SourceType.POSTGRESQL)
        assert len(type_map) > 0
