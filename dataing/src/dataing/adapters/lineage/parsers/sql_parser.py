"""SQL lineage parser using sqlglot.

Extracts table-level and column-level lineage from SQL statements.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ParsedLineage:
    """Result of parsing SQL for lineage.

    Attributes:
        inputs: List of input table names.
        outputs: List of output table names.
        column_lineage: Map of output column to source columns.
    """

    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    column_lineage: dict[str, list[tuple[str, str]]] = field(default_factory=dict)


class SQLLineageParser:
    """SQL lineage parser.

    Uses sqlglot when available, falls back to regex parsing otherwise.

    Attributes:
        dialect: SQL dialect for parsing.
    """

    def __init__(self, dialect: str = "snowflake") -> None:
        """Initialize the parser.

        Args:
            dialect: SQL dialect (snowflake, postgres, bigquery, etc.).
        """
        self._dialect = dialect
        self._has_sqlglot = self._check_sqlglot()

    def _check_sqlglot(self) -> bool:
        """Check if sqlglot is available.

        Returns:
            True if sqlglot is importable.
        """
        try:
            import sqlglot  # noqa: F401

            return True
        except ImportError:
            logger.warning("sqlglot not installed, using regex fallback for SQL parsing")
            return False

    def parse(self, sql: str) -> ParsedLineage:
        """Parse SQL to extract lineage.

        Args:
            sql: SQL statement(s) to parse.

        Returns:
            ParsedLineage with inputs and outputs.
        """
        if self._has_sqlglot:
            return self._parse_with_sqlglot(sql)
        return self._parse_with_regex(sql)

    def _parse_with_sqlglot(self, sql: str) -> ParsedLineage:
        """Parse SQL using sqlglot.

        Args:
            sql: SQL to parse.

        Returns:
            ParsedLineage result.
        """
        import sqlglot
        from sqlglot import exp

        result = ParsedLineage()
        inputs: set[str] = set()
        outputs: set[str] = set()

        try:
            statements = sqlglot.parse(sql, dialect=self._dialect)

            for statement in statements:
                if statement is None:
                    continue

                # Process based on statement type
                if isinstance(statement, exp.Create):
                    self._process_create(statement, inputs, outputs)
                elif isinstance(statement, exp.Insert):
                    self._process_insert(statement, inputs, outputs)
                elif isinstance(statement, exp.Merge):
                    self._process_merge(statement, inputs, outputs)
                elif isinstance(statement, exp.Select):
                    # Standalone SELECT doesn't have an output
                    self._extract_source_tables(statement, inputs)
                else:
                    # For other statements, try to extract any table references
                    self._extract_source_tables(statement, inputs)

            result.inputs = list(inputs - outputs)
            result.outputs = list(outputs)

        except Exception as e:
            logger.warning(f"Failed to parse SQL with sqlglot: {e}")
            # Fall back to regex
            return self._parse_with_regex(sql)

        return result

    def _process_create(self, statement: Any, inputs: set[str], outputs: set[str]) -> None:
        """Process CREATE statement.

        Args:
            statement: sqlglot Create expression.
            inputs: Set to add input tables to.
            outputs: Set to add output tables to.
        """
        from sqlglot import exp

        # Get the target table
        table = statement.this
        if isinstance(table, exp.Table):
            table_name = self._get_table_name(table)
            if table_name:
                outputs.add(table_name)

        # Get source tables from the AS clause (CREATE TABLE AS SELECT)
        if statement.expression:
            self._extract_source_tables(statement.expression, inputs)

    def _process_insert(self, statement: Any, inputs: set[str], outputs: set[str]) -> None:
        """Process INSERT statement.

        Args:
            statement: sqlglot Insert expression.
            inputs: Set to add input tables to.
            outputs: Set to add output tables to.
        """
        from sqlglot import exp

        # Get the target table
        table = statement.this
        if isinstance(table, exp.Table):
            table_name = self._get_table_name(table)
            if table_name:
                outputs.add(table_name)

        # Get source tables from SELECT
        if statement.expression:
            self._extract_source_tables(statement.expression, inputs)

    def _process_merge(self, statement: Any, inputs: set[str], outputs: set[str]) -> None:
        """Process MERGE statement.

        Args:
            statement: sqlglot Merge expression.
            inputs: Set to add input tables to.
            outputs: Set to add output tables to.
        """
        from sqlglot import exp

        # Get the target table (INTO clause)
        if hasattr(statement, "this") and isinstance(statement.this, exp.Table):
            table_name = self._get_table_name(statement.this)
            if table_name:
                outputs.add(table_name)

        # Get source table (USING clause)
        if hasattr(statement, "using") and statement.using:
            self._extract_source_tables(statement.using, inputs)

    def _extract_source_tables(self, expression: Any, tables: set[str]) -> None:
        """Extract all source tables from an expression.

        Args:
            expression: sqlglot expression to search.
            tables: Set to add found tables to.
        """
        from sqlglot import exp

        if expression is None:
            return

        for table in expression.find_all(exp.Table):
            table_name = self._get_table_name(table)
            if table_name:
                tables.add(table_name)

    def _get_table_name(self, table: Any) -> str | None:
        """Extract fully qualified table name.

        Args:
            table: sqlglot Table expression.

        Returns:
            Fully qualified table name or None.
        """
        parts = []

        if hasattr(table, "catalog") and table.catalog:
            parts.append(str(table.catalog))
        if hasattr(table, "db") and table.db:
            parts.append(str(table.db))
        if hasattr(table, "name") and table.name:
            parts.append(str(table.name))

        return ".".join(parts) if parts else None

    def _parse_with_regex(self, sql: str) -> ParsedLineage:
        """Parse SQL using regex patterns.

        This is a fallback when sqlglot is not available.

        Args:
            sql: SQL to parse.

        Returns:
            ParsedLineage result.
        """
        result = ParsedLineage()
        inputs: set[str] = set()
        outputs: set[str] = set()

        # Normalize whitespace
        sql = " ".join(sql.split())

        # Match CREATE TABLE/VIEW
        create_pattern = (
            r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?"
            r"(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"([a-zA-Z_][a-zA-Z0-9_\.]*)"
        )
        for match in re.finditer(create_pattern, sql, re.IGNORECASE):
            outputs.add(match.group(1))

        # Match INSERT INTO
        insert_pattern = r"INSERT\s+(?:OVERWRITE\s+)?(?:INTO\s+)?([a-zA-Z_][a-zA-Z0-9_\.]*)"
        for match in re.finditer(insert_pattern, sql, re.IGNORECASE):
            outputs.add(match.group(1))

        # Match MERGE INTO
        merge_pattern = r"MERGE\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_\.]*)"
        for match in re.finditer(merge_pattern, sql, re.IGNORECASE):
            outputs.add(match.group(1))

        # Match FROM clause tables
        from_pattern = r"FROM\s+([a-zA-Z_][a-zA-Z0-9_\.]*)"
        for match in re.finditer(from_pattern, sql, re.IGNORECASE):
            table = match.group(1)
            # Skip common keywords that might follow FROM
            if table.upper() not in ("SELECT", "WHERE", "GROUP", "ORDER", "HAVING"):
                inputs.add(table)

        # Match JOIN tables
        join_pattern = r"JOIN\s+([a-zA-Z_][a-zA-Z0-9_\.]*)"
        for match in re.finditer(join_pattern, sql, re.IGNORECASE):
            inputs.add(match.group(1))

        # Match USING clause in MERGE
        using_pattern = r"USING\s+([a-zA-Z_][a-zA-Z0-9_\.]*)"
        for match in re.finditer(using_pattern, sql, re.IGNORECASE):
            inputs.add(match.group(1))

        # Remove outputs from inputs
        result.inputs = list(inputs - outputs)
        result.outputs = list(outputs)

        return result

    def get_column_lineage(
        self, sql: str, target_table: str | None = None
    ) -> dict[str, list[tuple[str, str]]]:
        """Extract column-level lineage from SQL.

        This is a more advanced feature that traces which source columns
        feed into which output columns.

        Args:
            sql: SQL to analyze.
            target_table: Optional target table to focus on.

        Returns:
            Dict mapping output column to list of (source_table, source_column).
        """
        if not self._has_sqlglot:
            return {}

        try:
            import sqlglot
            from sqlglot.lineage import lineage

            # sqlglot has a lineage module for column-level tracking
            result: dict[str, list[tuple[str, str]]] = {}

            statements = sqlglot.parse(sql, dialect=self._dialect)

            for statement in statements:
                if statement is None:
                    continue

                # Use sqlglot's lineage function for each column
                # This is a simplified version - full implementation would
                # need to handle all expression types
                try:
                    for select in statement.find_all(sqlglot.exp.Select):
                        for expr in select.expressions:
                            if hasattr(expr, "alias_or_name"):
                                col_name = expr.alias_or_name
                                # Get lineage for this column
                                col_lineage = lineage(
                                    col_name,
                                    sql,
                                    dialect=self._dialect,
                                )
                                if col_lineage:
                                    result[col_name] = [
                                        (str(node.source.sql()), str(node.name))
                                        for node in col_lineage.walk()
                                        if hasattr(node, "source") and node.source
                                    ]
                except Exception:
                    # Column lineage is complex and may fail on some SQL
                    continue

            return result

        except Exception as e:
            logger.warning(f"Failed to extract column lineage: {e}")
            return {}
