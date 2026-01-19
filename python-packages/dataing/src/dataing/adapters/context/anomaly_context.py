"""Anomaly Context - Confirms and profiles anomalies in data.

This module verifies that reported anomalies actually exist in the data
and profiles the affected columns to provide context for investigation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from dataing.adapters.datasource.sql.base import SQLAdapter
    from dataing.core.domain_types import AnomalyAlert

logger = structlog.get_logger()


@dataclass
class AnomalyConfirmation:
    """Result of anomaly confirmation check.

    Attributes:
        exists: Whether the anomaly was confirmed in the data.
        actual_value: The observed value from the data.
        expected_range: Expected value range based on historical data.
        sample_rows: Sample of affected rows.
        profile: Column profile statistics.
        message: Human-readable confirmation message.
    """

    exists: bool
    actual_value: float | None
    expected_range: tuple[float, float] | None
    sample_rows: list[dict[str, Any]]
    profile: dict[str, Any]
    message: str


@dataclass
class ColumnProfile:
    """Statistical profile of a column.

    Attributes:
        total_count: Total row count.
        null_count: Number of NULL values.
        null_rate: Percentage of NULL values.
        distinct_count: Number of distinct values.
        min_value: Minimum value (if applicable).
        max_value: Maximum value (if applicable).
        avg_value: Average value (if numeric).
    """

    total_count: int
    null_count: int
    null_rate: float
    distinct_count: int
    min_value: Any | None = None
    max_value: Any | None = None
    avg_value: float | None = None


class AnomalyContext:
    """Confirms anomalies and profiles affected data.

    This class is responsible for:
    1. Verifying anomalies exist in the actual data
    2. Profiling affected columns
    3. Providing sample data for investigation context
    """

    def __init__(self, sample_size: int = 10) -> None:
        """Initialize the anomaly context.

        Args:
            sample_size: Number of sample rows to retrieve.
        """
        self.sample_size = sample_size

    async def confirm(
        self,
        adapter: SQLAdapter,
        anomaly: AnomalyAlert,
    ) -> AnomalyConfirmation:
        """Confirm that an anomaly exists in the data.

        Args:
            adapter: Connected database adapter.
            anomaly: The anomaly alert to verify.

        Returns:
            AnomalyConfirmation with verification results.
        """
        logger.info(
            "confirming_anomaly",
            dataset=anomaly.dataset_id,
            metric=anomaly.metric_spec.display_name,
            anomaly_type=anomaly.anomaly_type,
            date=anomaly.anomaly_date,
        )

        # Use structured metric_spec to determine what to check
        spec = anomaly.metric_spec
        is_null_rate = "null" in anomaly.anomaly_type.lower()

        # Get column name from metric_spec
        if spec.metric_type == "column":
            column_name = spec.expression
        elif spec.columns_referenced:
            column_name = spec.columns_referenced[0]
        else:
            column_name = self._extract_column_name(spec.display_name, anomaly.dataset_id)

        try:
            if is_null_rate:
                return await self._confirm_null_rate_anomaly(adapter, anomaly, column_name)
            elif "row_count" in anomaly.anomaly_type.lower():
                return await self._confirm_row_count_anomaly(adapter, anomaly)
            else:
                # Generic metric confirmation
                return await self._confirm_generic_anomaly(adapter, anomaly, column_name)
        except Exception as e:
            logger.error("anomaly_confirmation_failed", error=str(e))
            return AnomalyConfirmation(
                exists=False,
                actual_value=None,
                expected_range=None,
                sample_rows=[],
                profile={},
                message=f"Failed to confirm anomaly: {e}",
            )

    async def _confirm_null_rate_anomaly(
        self,
        adapter: SQLAdapter,
        anomaly: AnomalyAlert,
        column_name: str,
    ) -> AnomalyConfirmation:
        """Confirm a NULL rate anomaly.

        Args:
            adapter: Connected database adapter.
            anomaly: The anomaly alert.
            column_name: Name of the column to check.

        Returns:
            AnomalyConfirmation for NULL rate check.
        """
        table_name = anomaly.dataset_id

        # Query to check NULL rate on the anomaly date
        null_query = f"""
        SELECT
            COUNT(*) as total_count,
            SUM(CASE WHEN {column_name} IS NULL THEN 1 ELSE 0 END) as null_count,
            ROUND(100.0 * SUM(CASE WHEN {column_name} IS NULL
                THEN 1 ELSE 0 END) / COUNT(*), 2) as null_rate
        FROM {table_name}
        WHERE DATE(created_at) = '{anomaly.anomaly_date}'
        """

        result = await adapter.execute_query(null_query)

        if not result.rows:
            return AnomalyConfirmation(
                exists=False,
                actual_value=None,
                expected_range=None,
                sample_rows=[],
                profile={},
                message=f"No data found for {table_name} on {anomaly.anomaly_date}",
            )

        row = result.rows[0]
        actual_null_rate = row.get("null_rate", 0)
        total_count = row.get("total_count", 0)
        null_count = row.get("null_count", 0)

        # Get sample of NULL rows
        sample_query = f"""
        SELECT *
        FROM {table_name}
        WHERE DATE(created_at) = '{anomaly.anomaly_date}'
          AND {column_name} IS NULL
        LIMIT {self.sample_size}
        """

        sample_result = await adapter.execute_query(sample_query)
        sample_rows = [dict(r) for r in sample_result.rows]

        # Determine if anomaly is confirmed
        threshold = anomaly.expected_value * 2 if anomaly.expected_value > 0 else 5
        exists = actual_null_rate >= threshold

        return AnomalyConfirmation(
            exists=exists,
            actual_value=actual_null_rate,
            expected_range=(0, anomaly.expected_value),
            sample_rows=sample_rows,
            profile={
                "total_count": total_count,
                "null_count": null_count,
                "null_rate": actual_null_rate,
                "column": column_name,
                "date": anomaly.anomaly_date,
            },
            message=(
                f"""Confirmed: {column_name} has {actual_null_rate}% NULL
                    rate on {anomaly.anomaly_date} """
                f"({null_count}/{total_count} rows)"
                if exists
                else f"""Not confirmed: {column_name} has {actual_null_rate}% NULL rate,
                    expected >{threshold}%"""
            ),
        )

    async def _confirm_row_count_anomaly(
        self,
        adapter: SQLAdapter,
        anomaly: AnomalyAlert,
    ) -> AnomalyConfirmation:
        """Confirm a row count anomaly.

        Args:
            adapter: Connected database adapter.
            anomaly: The anomaly alert.

        Returns:
            AnomalyConfirmation for row count check.
        """
        table_name = anomaly.dataset_id

        count_query = f"""
        SELECT COUNT(*) as row_count
        FROM {table_name}
        WHERE DATE(created_at) = '{anomaly.anomaly_date}'
        """

        result = await adapter.execute_query(count_query)

        if not result.rows:
            return AnomalyConfirmation(
                exists=False,
                actual_value=None,
                expected_range=None,
                sample_rows=[],
                profile={},
                message=f"No data found for {table_name} on {anomaly.anomaly_date}",
            )

        actual_count = result.rows[0].get("row_count", 0)
        deviation = abs(actual_count - anomaly.expected_value) / anomaly.expected_value * 100

        exists = deviation >= abs(anomaly.deviation_pct) * 0.5  # Allow some tolerance

        return AnomalyConfirmation(
            exists=exists,
            actual_value=actual_count,
            expected_range=(anomaly.expected_value * 0.9, anomaly.expected_value * 1.1),
            sample_rows=[],
            profile={
                "actual_count": actual_count,
                "expected_count": anomaly.expected_value,
                "deviation_pct": deviation,
                "date": anomaly.anomaly_date,
            },
            message=(
                f"Confirmed: {table_name} has {actual_count} rows on {anomaly.anomaly_date}, "
                f"expected ~{anomaly.expected_value}"
                if exists
                else f"Not confirmed: row count {actual_count} is within expected range"
            ),
        )

    async def _confirm_generic_anomaly(
        self,
        adapter: SQLAdapter,
        anomaly: AnomalyAlert,
        column_name: str,
    ) -> AnomalyConfirmation:
        """Confirm a generic metric anomaly.

        Args:
            adapter: Connected database adapter.
            anomaly: The anomaly alert.
            column_name: Column to analyze.

        Returns:
            AnomalyConfirmation for generic check.
        """
        # Just profile the column for generic anomalies
        profile = await self.profile_column(
            adapter,
            anomaly.dataset_id,
            column_name,
            anomaly.anomaly_date,
        )

        return AnomalyConfirmation(
            exists=True,  # Assume exists, let investigation verify
            actual_value=anomaly.actual_value,
            expected_range=(anomaly.expected_value * 0.8, anomaly.expected_value * 1.2),
            sample_rows=[],
            profile=profile.__dict__,
            message=f"""Generic anomaly for {column_name}: actual={anomaly.actual_value},
                expected={anomaly.expected_value}""",
        )

    async def profile_column(
        self,
        adapter: SQLAdapter,
        table_name: str,
        column_name: str,
        date: str | None = None,
    ) -> ColumnProfile:
        """Get statistical profile for a column.

        Args:
            adapter: Connected database adapter.
            table_name: Name of the table.
            column_name: Name of the column.
            date: Optional date filter.

        Returns:
            ColumnProfile with statistics.
        """
        date_filter = f"WHERE DATE(created_at) = '{date}'" if date else ""

        profile_query = f"""
        SELECT
            COUNT(*) as total_count,
            SUM(CASE WHEN {column_name} IS NULL THEN 1 ELSE 0 END) as null_count,
            ROUND(100.0 * SUM(CASE WHEN {column_name} IS NULL THEN 1 ELSE 0 END)
                / COUNT(*), 2) as null_rate,
            COUNT(DISTINCT {column_name}) as distinct_count
        FROM {table_name}
        {date_filter}
        """

        result = await adapter.execute_query(profile_query)

        if not result.rows:
            return ColumnProfile(
                total_count=0,
                null_count=0,
                null_rate=0,
                distinct_count=0,
            )

        row = result.rows[0]
        return ColumnProfile(
            total_count=row.get("total_count", 0),
            null_count=row.get("null_count", 0),
            null_rate=row.get("null_rate", 0),
            distinct_count=row.get("distinct_count", 0),
        )

    def _extract_column_name(self, metric_name: str, dataset_id: str) -> str:
        """Extract column name from metric name.

        Args:
            metric_name: The metric name (e.g., "user_id_null_rate").
            dataset_id: The dataset/table name for context.

        Returns:
            Extracted column name.
        """
        # Common patterns: column_null_rate, null_rate_column, column_metric
        metric_lower = metric_name.lower()

        # Remove common suffixes
        for suffix in ["_null_rate", "_rate", "_count", "_avg", "_sum", "_null"]:
            if metric_lower.endswith(suffix):
                return metric_name[: -len(suffix)]

        # Remove common prefixes
        for prefix in ["null_rate_", "null_", "rate_"]:
            if metric_lower.startswith(prefix):
                return metric_name[len(prefix) :]

        # Default: assume metric name is the column name
        return metric_name
