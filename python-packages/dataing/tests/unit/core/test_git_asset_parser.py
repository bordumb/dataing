"""Unit tests for git asset parser functions."""

from __future__ import annotations

from dataing.core.git_asset_parser import (
    extract_dbt_refs,
    extract_sql_tables,
    parse_affected_assets,
)


class TestExtractDbtRefs:
    """Tests for extract_dbt_refs function."""

    def test_single_ref(self) -> None:
        """Test extracting a single dbt ref."""
        diff = """+SELECT * FROM {{ ref('orders') }}"""
        result = extract_dbt_refs("models/example.sql", diff)
        assert result == ["orders"]

    def test_multiple_refs(self) -> None:
        """Test extracting multiple dbt refs."""
        diff = """
+SELECT * FROM {{ ref('orders') }}
+JOIN {{ ref('customers') }} ON orders.customer_id = customers.id
"""
        result = extract_dbt_refs("models/example.sql", diff)
        assert result == ["orders", "customers"]

    def test_source_call(self) -> None:
        """Test extracting source() calls."""
        diff = """+SELECT * FROM {{ source('raw', 'events') }}"""
        result = extract_dbt_refs("models/staging/stg_events.sql", diff)
        assert result == ["raw.events"]

    def test_with_alias(self) -> None:
        """Test extracting alias from config."""
        diff = """
+{{ config(materialized='table', alias='orders_final') }}
+SELECT * FROM {{ ref('orders') }}
"""
        result = extract_dbt_refs("models/orders.sql", diff)
        assert "orders_final" in result
        assert "orders" in result

    def test_double_quotes(self) -> None:
        """Test dbt refs with double quotes."""
        diff = """+SELECT * FROM {{ ref("orders") }}"""
        result = extract_dbt_refs("models/example.sql", diff)
        assert result == ["orders"]

    def test_no_match(self) -> None:
        """Test with no dbt refs."""
        diff = """+SELECT * FROM orders"""
        result = extract_dbt_refs("models/example.sql", diff)
        assert result == []

    def test_only_added_lines(self) -> None:
        """Test that only added lines are parsed."""
        diff = """
-SELECT * FROM {{ ref('old_model') }}
+SELECT * FROM {{ ref('new_model') }}
"""
        result = extract_dbt_refs("models/example.sql", diff)
        assert result == ["new_model"]
        assert "old_model" not in result

    def test_deduplication(self) -> None:
        """Test that duplicate refs are deduplicated."""
        diff = """
+SELECT * FROM {{ ref('orders') }}
+UNION ALL
+SELECT * FROM {{ ref('orders') }}
"""
        result = extract_dbt_refs("models/example.sql", diff)
        assert result == ["orders"]


class TestExtractSqlTables:
    """Tests for extract_sql_tables function."""

    def test_from_select(self) -> None:
        """Test extracting table from SELECT statement."""
        diff = """+SELECT * FROM orders"""
        result = extract_sql_tables(diff)
        assert result == ["orders"]

    def test_from_join(self) -> None:
        """Test extracting tables from JOIN."""
        diff = """
+SELECT *
+FROM orders
+LEFT JOIN customers ON orders.customer_id = customers.id
"""
        result = extract_sql_tables(diff)
        assert "orders" in result
        assert "customers" in result

    def test_from_insert(self) -> None:
        """Test extracting table from INSERT."""
        diff = """+INSERT INTO target_table SELECT * FROM source"""
        result = extract_sql_tables(diff)
        assert "target_table" in result
        assert "source" in result

    def test_from_create(self) -> None:
        """Test extracting table from CREATE TABLE."""
        diff = """+CREATE TABLE new_table AS SELECT * FROM old_table"""
        result = extract_sql_tables(diff)
        assert "new_table" in result
        assert "old_table" in result

    def test_schema_qualified(self) -> None:
        """Test schema-qualified table names."""
        diff = """+SELECT * FROM public.orders"""
        result = extract_sql_tables(diff)
        assert result == ["public.orders"]

    def test_catalog_schema_table(self) -> None:
        """Test fully qualified table names."""
        diff = """+SELECT * FROM analytics.public.orders"""
        result = extract_sql_tables(diff)
        assert result == ["analytics.public.orders"]

    def test_deduplication(self) -> None:
        """Test that duplicate tables are removed."""
        diff = """
+SELECT * FROM orders
+UNION ALL
+SELECT * FROM orders
"""
        result = extract_sql_tables(diff)
        assert result.count("orders") == 1

    def test_case_insensitive(self) -> None:
        """Test case insensitivity."""
        diff = """+SELECT * FROM ORDERS"""
        result = extract_sql_tables(diff)
        assert result == ["orders"]

    def test_update_statement(self) -> None:
        """Test extracting table from UPDATE."""
        diff = """+UPDATE orders SET status = 'shipped'"""
        result = extract_sql_tables(diff)
        assert result == ["orders"]

    def test_drop_table(self) -> None:
        """Test extracting table from DROP TABLE."""
        diff = """+DROP TABLE IF EXISTS old_orders"""
        result = extract_sql_tables(diff)
        assert result == ["old_orders"]

    def test_create_view(self) -> None:
        """Test extracting view from CREATE VIEW."""
        diff = """+CREATE OR REPLACE VIEW orders_view AS SELECT * FROM orders"""
        result = extract_sql_tables(diff)
        assert "orders_view" in result
        assert "orders" in result

    def test_filters_keywords(self) -> None:
        """Test that SQL keywords are filtered out."""
        # This could happen if FROM is followed by a subquery without parentheses
        diff = """+SELECT * FROM orders WHERE true"""
        result = extract_sql_tables(diff)
        assert "orders" in result
        assert "true" not in result
        assert "where" not in result


class TestParseAffectedAssets:
    """Tests for parse_affected_assets function."""

    def test_sql_file(self) -> None:
        """Test parsing SQL file."""
        diff = """+SELECT * FROM orders"""
        result = parse_affected_assets("scripts/query.sql", diff)
        assert len(result) == 1
        assert result[0]["name"] == "orders"
        assert result[0]["type"] == "table"
        assert result[0]["source"] == "sql_parse"

    def test_dbt_model(self) -> None:
        """Test parsing dbt model file."""
        diff = """
+SELECT *
+FROM {{ ref('orders') }}
+JOIN public.customers ON true
"""
        result = parse_affected_assets("models/staging/stg_orders.sql", diff)

        # Should have dbt ref and sql table
        names = [a["name"] for a in result]
        assert "orders" in names
        assert "public.customers" in names

        # Check sources are correct
        dbt_ref = next(a for a in result if a["name"] == "orders")
        sql_table = next(a for a in result if a["name"] == "public.customers")
        assert dbt_ref["source"] == "dbt_ref"
        assert sql_table["source"] == "sql_parse"

    def test_python_file(self) -> None:
        """Test parsing Python file with SQL."""
        diff = """+cursor.execute("SELECT * FROM users")"""
        result = parse_affected_assets("scripts/etl.py", diff)
        assert len(result) == 1
        assert result[0]["name"] == "users"
        assert result[0]["source"] == "python_sql"

    def test_unknown_file(self) -> None:
        """Test parsing unknown file type returns empty."""
        diff = """+some content"""
        result = parse_affected_assets("config.yaml", diff)
        assert result == []

    def test_none_diff(self) -> None:
        """Test with None diff content."""
        result = parse_affected_assets("models/test.sql", None)
        assert result == []

    def test_only_added_lines(self) -> None:
        """Test that only added lines are parsed."""
        diff = """
-SELECT * FROM old_table
+SELECT * FROM new_table
"""
        result = parse_affected_assets("query.sql", diff)
        names = [a["name"] for a in result]
        assert "new_table" in names
        assert "old_table" not in names

    def test_dbt_path_variants(self) -> None:
        """Test various dbt path patterns are recognized."""
        diff = """+{{ ref('model') }}"""

        # Should recognize as dbt (patterns require "/" prefix for some)
        for path in [
            "models/staging/model.sql",
            "dbt/models/model.sql",
            "project/transform/model.sql",  # /transform/ pattern
            "project/dbt_project/models/model.sql",
        ]:
            result = parse_affected_assets(path, diff)
            dbt_refs = [a for a in result if a["source"] == "dbt_ref"]
            assert len(dbt_refs) > 0, f"Failed for path: {path}"

    def test_jinja_sql_extension(self) -> None:
        """Test .sql.jinja extension is recognized."""
        diff = """+{{ ref('model') }}"""
        result = parse_affected_assets("template.sql.jinja", diff)
        assert any(a["source"] == "dbt_ref" for a in result)

    def test_no_duplicate_assets(self) -> None:
        """Test that dbt refs don't create duplicate entries from SQL parse."""
        diff = """
+SELECT *
+FROM {{ ref('orders') }}
+LEFT JOIN orders ON true
"""
        result = parse_affected_assets("models/model.sql", diff)
        names = [a["name"] for a in result]
        # Should only have one 'orders' entry (from dbt_ref), not duplicate from sql_parse
        assert names.count("orders") == 1
