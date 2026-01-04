"""Tests for the SQL lineage parser."""

import pytest

from dataing.adapters.lineage.parsers.sql_parser import SQLLineageParser


def test_parse_simple_select():
    """Test parsing a simple SELECT statement."""
    parser = SQLLineageParser(dialect="snowflake")
    sql = "SELECT * FROM orders"

    result = parser.parse(sql)

    assert "orders" in result.inputs
    assert len(result.outputs) == 0


def test_parse_create_table_as():
    """Test parsing CREATE TABLE AS SELECT."""
    parser = SQLLineageParser(dialect="snowflake")
    sql = """
    CREATE TABLE analytics.summary AS
    SELECT customer_id, SUM(amount) as total
    FROM sales.orders
    JOIN sales.customers USING (customer_id)
    GROUP BY customer_id
    """

    result = parser.parse(sql)

    assert "analytics.summary" in result.outputs
    assert "sales.orders" in result.inputs or "orders" in result.inputs
    assert "sales.customers" in result.inputs or "customers" in result.inputs


def test_parse_insert_into():
    """Test parsing INSERT INTO statement."""
    parser = SQLLineageParser(dialect="snowflake")
    sql = """
    INSERT INTO target_table
    SELECT * FROM source_table
    """

    result = parser.parse(sql)

    assert "target_table" in result.outputs
    assert "source_table" in result.inputs


def test_parse_multiple_joins():
    """Test parsing statement with multiple JOINs."""
    parser = SQLLineageParser(dialect="snowflake")
    sql = """
    SELECT a.id, b.name, c.value
    FROM table_a a
    JOIN table_b b ON a.id = b.a_id
    LEFT JOIN table_c c ON b.id = c.b_id
    """

    result = parser.parse(sql)

    # All three tables should be in inputs
    input_names = [i.lower() for i in result.inputs]
    assert any("table_a" in i for i in input_names) or "a" in input_names
    assert any("table_b" in i for i in input_names) or "b" in input_names
    assert any("table_c" in i for i in input_names) or "c" in input_names


def test_parse_merge():
    """Test parsing MERGE statement."""
    parser = SQLLineageParser(dialect="snowflake")
    sql = """
    MERGE INTO target t
    USING source s ON t.id = s.id
    WHEN MATCHED THEN UPDATE SET t.value = s.value
    WHEN NOT MATCHED THEN INSERT (id, value) VALUES (s.id, s.value)
    """

    result = parser.parse(sql)

    # Target should be output, source should be input
    assert any("target" in o.lower() for o in result.outputs) or "t" in result.outputs
    assert any("source" in i.lower() for i in result.inputs) or "s" in result.inputs


def test_parse_with_fully_qualified_names():
    """Test parsing with fully qualified table names."""
    parser = SQLLineageParser(dialect="snowflake")
    sql = """
    CREATE OR REPLACE TABLE db.schema.target AS
    SELECT * FROM db.schema.source1
    JOIN db.other_schema.source2 USING (id)
    """

    result = parser.parse(sql)

    assert any("target" in o for o in result.outputs)
    assert len(result.inputs) >= 1


def test_parse_create_view():
    """Test parsing CREATE VIEW."""
    parser = SQLLineageParser(dialect="snowflake")
    sql = """
    CREATE OR REPLACE VIEW my_view AS
    SELECT * FROM base_table WHERE active = true
    """

    result = parser.parse(sql)

    assert any("my_view" in o for o in result.outputs)
    assert any("base_table" in i for i in result.inputs)


def test_regex_fallback():
    """Test that regex fallback works when sqlglot is not available."""
    parser = SQLLineageParser(dialect="unknown")
    # Force regex parsing
    parser._has_sqlglot = False

    sql = """
    CREATE TABLE output_table AS
    SELECT * FROM input_table1
    JOIN input_table2 ON input_table1.id = input_table2.id
    """

    result = parser._parse_with_regex(sql)

    assert "output_table" in result.outputs
    assert "input_table1" in result.inputs
    assert "input_table2" in result.inputs
