"""Correlation Context - Finds patterns across related tables.

This module analyzes relationships between tables and identifies
correlations that might explain anomalies, such as upstream data
issues or cross-table patterns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from dataing.adapters.datasource.types import SchemaResponse, Table

if TYPE_CHECKING:
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.core.domain_types import AnomalyAlert

logger = structlog.get_logger()


@dataclass
class Correlation:
    """A detected correlation between tables.

    Attributes:
        source_table: The primary table being investigated.
        related_table: A potentially related table.
        join_column: The column used to join tables.
        correlation_type: Type of correlation found.
        strength: Strength of correlation (0-1).
        description: Human-readable description.
        evidence_query: SQL query that demonstrates the correlation.
    """

    source_table: str
    related_table: str
    join_column: str
    correlation_type: str
    strength: float
    description: str
    evidence_query: str


@dataclass
class TimeSeriesPattern:
    """A pattern detected in time series data.

    Attributes:
        table: The table analyzed.
        column: The column analyzed.
        pattern_type: Type of pattern (spike, drop, trend).
        start_date: When the pattern started.
        end_date: When the pattern ended.
        severity: Severity of the pattern.
        data_points: Sample data points.
    """

    table: str
    column: str
    pattern_type: str
    start_date: str
    end_date: str
    severity: float
    data_points: list[dict[str, Any]]


class CorrelationContext:
    """Finds correlations and patterns across tables.

    This class is responsible for:
    1. Identifying related tables based on schema
    2. Finding correlations between anomalies and related data
    3. Analyzing time series patterns
    """

    def __init__(self, lookback_days: int = 7) -> None:
        """Initialize the correlation context.

        Args:
            lookback_days: Days to look back for time series analysis.
        """
        self.lookback_days = lookback_days

    async def find_correlations(
        self,
        adapter: BaseAdapter,
        anomaly: AnomalyAlert,
        schema: SchemaResponse,
    ) -> list[Correlation]:
        """Find correlations between the anomaly and related tables.

        Args:
            adapter: Connected data source adapter.
            anomaly: The anomaly to investigate.
            schema: SchemaResponse with table information.

        Returns:
            List of detected correlations.
        """
        logger.info(
            "finding_correlations",
            dataset=anomaly.dataset_id,
            date=anomaly.anomaly_date,
        )

        correlations: list[Correlation] = []

        # Get the target table from schema
        target_table = self._get_table(schema, anomaly.dataset_id)
        if not target_table:
            logger.warning("target_table_not_found", table=anomaly.dataset_id)
            return correlations

        # Find related tables
        related_tables = self._find_related_tables(schema, anomaly.dataset_id)

        for related in related_tables:
            try:
                correlation = await self._analyze_table_correlation(
                    adapter,
                    anomaly,
                    anomaly.dataset_id,
                    related["table"],
                    related["join_column"],
                )
                if correlation and correlation.strength > 0.3:
                    correlations.append(correlation)
            except Exception as e:
                logger.warning(
                    "correlation_analysis_failed",
                    related_table=related["table"],
                    error=str(e),
                )

        logger.info("correlations_found", count=len(correlations))
        return correlations

    async def analyze_time_series(
        self,
        adapter: BaseAdapter,
        table_name: str,
        column_name: str,
        center_date: str,
    ) -> TimeSeriesPattern | None:
        """Analyze time series data around an anomaly date.

        Args:
            adapter: Connected database adapter.
            table_name: Table to analyze.
            column_name: Column to analyze.
            center_date: The anomaly date to center analysis on.

        Returns:
            TimeSeriesPattern if pattern detected, None otherwise.
        """
        logger.info(
            "analyzing_time_series",
            table=table_name,
            column=column_name,
            date=center_date,
        )

        # Query for time series data
        query = f"""
        SELECT
            DATE(created_at) as date,
            COUNT(*) as total_count,
            SUM(CASE WHEN {column_name} IS NULL THEN 1 ELSE 0 END) as null_count,
            ROUND(100.0 * SUM(CASE WHEN {column_name} IS NULL THEN 1 ELSE 0 END)
                / COUNT(*), 2) as null_rate
        FROM {table_name}
        WHERE created_at >= DATE('{center_date}') - INTERVAL '{self.lookback_days}' DAY
          AND created_at <= DATE('{center_date}') + INTERVAL '{self.lookback_days}' DAY
        GROUP BY DATE(created_at)
        ORDER BY date
        """

        try:
            result = await adapter.execute_query(query)
        except Exception as e:
            logger.warning("time_series_query_failed", error=str(e))
            return None

        if not result.rows:
            return None

        data_points = [dict(r) for r in result.rows]

        # Detect pattern type
        pattern = self._detect_pattern(data_points, "null_rate")

        if not pattern:
            return None

        return TimeSeriesPattern(
            table=table_name,
            column=column_name,
            pattern_type=pattern["type"],
            start_date=pattern["start"],
            end_date=pattern["end"],
            severity=pattern["severity"],
            data_points=data_points,
        )

    async def find_upstream_anomalies(
        self,
        adapter: BaseAdapter,
        anomaly: AnomalyAlert,
        schema: SchemaResponse,
    ) -> list[dict[str, Any]]:
        """Find anomalies in upstream/related tables.

        Args:
            adapter: Connected database adapter.
            anomaly: The primary anomaly.
            schema: Schema context.

        Returns:
            List of upstream anomalies detected.
        """
        upstream_anomalies = []

        related_tables = self._find_related_tables(schema, anomaly.dataset_id)

        for related in related_tables:
            try:
                # Check NULL rates in related tables on same date
                query = f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN {related["join_column"]} IS NULL THEN 1 ELSE 0 END) as null_count,
                    ROUND(100.0 * SUM(CASE WHEN {related["join_column"]} IS NULL THEN 1 ELSE 0 END)
                        / COUNT(*), 2) as null_rate
                FROM {related["table"]}
                WHERE DATE(created_at) = '{anomaly.anomaly_date}'
                """

                result = await adapter.execute_query(query)

                if result.rows and result.rows[0].get("null_rate", 0) > 5:
                    upstream_anomalies.append(
                        {
                            "table": related["table"],
                            "column": related["join_column"],
                            "null_rate": result.rows[0]["null_rate"],
                            "total_rows": result.rows[0]["total"],
                        }
                    )
            except Exception as e:
                logger.debug("upstream_check_failed", table=related["table"], error=str(e))

        return upstream_anomalies

    def _get_all_tables(self, schema: SchemaResponse) -> list[Table]:
        """Extract all tables from the nested schema structure."""
        tables = []
        for catalog in schema.catalogs:
            for db_schema in catalog.schemas:
                tables.extend(db_schema.tables)
        return tables

    def _get_table(self, schema: SchemaResponse, table_name: str) -> Table | None:
        """Get a table by name from the schema."""
        table_name_lower = table_name.lower()
        for table in self._get_all_tables(schema):
            if (
                table.native_path.lower() == table_name_lower
                or table.name.lower() == table_name_lower
            ):
                return table
        return None

    def _find_related_tables(
        self,
        schema: SchemaResponse,
        target_table: str,
    ) -> list[dict[str, str]]:
        """Find tables related to the target table.

        Args:
            schema: SchemaResponse.
            target_table: The target table name.

        Returns:
            List of related table info with join columns.
        """
        target = self._get_table(schema, target_table)
        if not target:
            return []

        target_cols = {col.name for col in target.columns}
        related = []

        for table in self._get_all_tables(schema):
            if table.name == target.name:
                continue

            table_cols = {col.name for col in table.columns}
            shared = target_cols & table_cols

            # Look for ID columns that could be join keys
            for col in shared:
                if col.endswith("_id") or col == "id":
                    related.append(
                        {
                            "table": table.native_path,
                            "join_column": col,
                        }
                    )
                    break

        return related

    async def _analyze_table_correlation(
        self,
        adapter: BaseAdapter,
        anomaly: AnomalyAlert,
        source_table: str,
        related_table: str,
        join_column: str,
    ) -> Correlation | None:
        """Analyze correlation between two tables.

        Args:
            adapter: Connected database adapter.
            anomaly: The anomaly being investigated.
            source_table: The primary table.
            related_table: The related table.
            join_column: Column to join on.

        Returns:
            Correlation if significant, None otherwise.
        """
        # Check if NULL values in source correlate with missing records in related
        query = f"""
        SELECT
            COUNT(s.{join_column}) as source_count,
            COUNT(r.{join_column}) as matched_count,
            COUNT(s.{join_column}) - COUNT(r.{join_column}) as unmatched_count,
            ROUND(100.0 * (COUNT(s.{join_column}) - COUNT(r.{join_column}))
                / NULLIF(COUNT(s.{join_column}), 0), 2) as unmatched_rate
        FROM {source_table} s
        LEFT JOIN {related_table} r ON s.{join_column} = r.{join_column}
        WHERE DATE(s.created_at) = '{anomaly.anomaly_date}'
          AND s.{join_column} IS NOT NULL
        """

        try:
            result = await adapter.execute_query(query)
        except Exception:
            return None

        if not result.rows:
            return None

        row = result.rows[0]
        unmatched_rate = row.get("unmatched_rate", 0) or 0

        if unmatched_rate < 10:  # Less than 10% unmatched is not significant
            return None

        strength = min(unmatched_rate / 100, 1.0)

        return Correlation(
            source_table=source_table,
            related_table=related_table,
            join_column=join_column,
            correlation_type="missing_reference",
            strength=strength,
            description=(
                f"{unmatched_rate}% of {source_table}.{join_column} values "
                f"have no matching record in {related_table}"
            ),
            evidence_query=query,
        )

    def _detect_pattern(
        self,
        data_points: list[dict[str, Any]],
        value_column: str,
    ) -> dict[str, Any] | None:
        """Detect pattern in time series data.

        Args:
            data_points: List of data points with date and value.
            value_column: The column containing values to analyze.

        Returns:
            Pattern info if detected, None otherwise.
        """
        if len(data_points) < 3:
            return None

        values = [p.get(value_column, 0) or 0 for p in data_points]
        dates = [str(p.get("date", "")) for p in data_points]

        # Calculate baseline (median of first few points)
        baseline = sorted(values[:3])[1] if len(values) >= 3 else values[0]

        # Find spike (value significantly above baseline)
        max_val = max(values)
        max_idx = values.index(max_val)

        if baseline > 0 and max_val > baseline * 3:
            # Find spike duration
            start_idx = max_idx
            end_idx = max_idx

            # Extend backwards while still elevated
            while start_idx > 0 and values[start_idx - 1] > baseline * 2:
                start_idx -= 1

            # Extend forwards while still elevated
            while end_idx < len(values) - 1 and values[end_idx + 1] > baseline * 2:
                end_idx += 1

            return {
                "type": "spike",
                "start": dates[start_idx],
                "end": dates[end_idx],
                "severity": min((max_val - baseline) / baseline, 10),
            }

        # Find drop (value significantly below baseline)
        min_val = min(values)
        min_idx = values.index(min_val)

        if baseline > 0 and min_val < baseline * 0.5:
            return {
                "type": "drop",
                "start": dates[min_idx],
                "end": dates[min_idx],
                "severity": (baseline - min_val) / baseline,
            }

        return None
